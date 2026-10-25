"""FastAPI backend: the same flow as scripts/run_graph.py, over HTTP (for the Next.js frontend).

Run from the backend/ folder:
    uv run uvicorn ai_decision_arena.api.main:app --port 8000
Then open http://localhost:8000/docs (Swagger UI: try every endpoint from the browser).

Flow:
    POST /api/decisions                   → 202 {thread_id}; the graph runs in the background
    GET  /api/decisions/{id}              → poll every ~2 s: run_state, progress lines, pending pause
    POST /api/decisions/{id}/resume       → answer the pending pause (or "continue" an interrupted run)
    GET  /api/decisions/{id}/report       → the final report, once finished
    GET  /api/decisions/{id}/brief        → the validated problem statement + solution brief
    GET  /api/decisions/{id}/plan         → the implementation plan (from the plan review on)
    GET  /api/decisions/{id}/artifacts    → approved versions of the brief and the plan
    GET  /api/decisions/{id}/evidence     → kept evidence with verification status
    GET  /api/decisions/{id}/live         → everything produced so far (case, evidence counts, plans, scores, verdicts)
    GET  /api/decisions                   → recent sessions (from the app tables); ?mode=quick for the chat list
    GET  /api/chats/{id}                  → patient chat transcript (api/chat.py)
    POST /api/chats/{id}/messages         → send a chat message; the reply streams back as text (api/chat.py)
    GET / DELETE /api/memories            → what the agents remember about this browser's patient (api/memories.py)
    POST /api/triggers/check-ins          → run the check-in trigger now (api/triggers.py; also runs on a schedule)

Status and pending pause are read from the checkpoint (graph.get_state), so they survive a restart.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from collections import Counter
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_decision_arena import memory
from ai_decision_arena.api.chat import router as chat_router
from ai_decision_arena.api.memories import router as memories_router
from ai_decision_arena.api.runner import GraphRunner, graph_config
from ai_decision_arena.api.triggers import router as triggers_router
from ai_decision_arena.api.errors import ApiError
from ai_decision_arena.api.schemas import (
    Accepted,
    CaseView,
    ClarificationResume,
    ContinueResume,
    Counters,
    CreateDecisionRequest,
    DebateView,
    DecisionStatus,
    ErrorResponse,
    EvidenceResponse,
    LiveSnapshot,
    PendingPause,
    ReportResponse,
    ArtifactList,
    ArtifactView,
    BriefResponse,
    BriefReviewResume,
    PlanResponse,
    PlanReviewResume,
    ResearchView,
    ResumeRequest,
    SessionList,
    SessionSummary,
    VerificationView,
)
from ai_decision_arena.config import get_settings
from ai_decision_arena.brief import brief_is_approved
from ai_decision_arena.plan import plan_is_approved
from ai_decision_arena.db.repository import list_artifacts, list_sessions, save_session_status
from ai_decision_arena.graph import build_graph
from ai_decision_arena.llm import resolve_model
from ai_decision_arena.memory import valid_user_id
from ai_decision_arena.triggers import CheckInScheduler
from ai_decision_arena.workspace.processes import ProcessManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# --- startup / shutdown ------------------------------------------------------------------------

def check_models() -> None:
    """Startup check (never assume a model exists): log whether the planner / implementer models are available to
    this API key. The planner re-checks per call and falls back to the default model with a progress line."""
    log = logging.getLogger(__name__)
    settings = get_settings()
    for role, wanted in (("planner", settings.planner_model), ("implementer", settings.implementer_model)):
        model, note = resolve_model(wanted)
        if note:
            log.warning("%s model: %s", role, note)
        else:
            log.info("%s model %s is available", role, model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after it).
    A connection POOL instead of 7.2's single connection: several requests and background runs use the
    checkpointer at the same time, and one psycopg connection must not be shared between threads."""
    pool = ConnectionPool(
        get_settings().database_url,
        min_size=1,
        max_size=10,
        # What PostgresSaver needs from every connection (same as PostgresSaver.from_conn_string sets up).
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()                                   # creates LangGraph's tables if missing (safe every time)
    graph = build_graph(checkpointer=saver)
    app.state.graph = graph
    app.state.runner = GraphRunner(graph)
    check_models()
    # Dev servers (M7): adopt the ones still running from before a restart, clean up what a crash left behind.
    # They are NOT stopped at shutdown, so `uvicorn --reload` keeps the previews alive (idle stop ends them).
    app.state.processes = ProcessManager()
    app.state.processes.reconcile()
    scheduler = CheckInScheduler(graph) if get_settings().check_ins_enabled else None   # scheduled trigger
    if scheduler:
        scheduler.start()
    yield
    if scheduler:
        scheduler.stop()
    pool.close()


app = FastAPI(
    title="AI App Builder API",
    version="0.9.0",
    description="Describe an app or website; answer the agents' questions; review the brief and the plan; watch the build.",
    lifespan=lifespan,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
# The Next.js dev server (Phase 9) runs on another port, so the browser needs CORS permission:
# the configured FRONTEND_URL plus any localhost port (so a second dev server on :3001 works too).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat_router)
app.include_router(memories_router)
app.include_router(triggers_router)


# --- errors: always {"error": {"code", "message"}} ---------------------------------------------

def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _error(exc.status_code, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """FastAPI's own 422 (bad body) in our error shape. Message like "body.action: Input should be ..."."""
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:3]]
    return _error(422, "invalid_input", "; ".join(parts))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """E.g. a URL that does not exist (404) or a wrong method (405)."""
    return _error(exc.status_code, "http_error", str(exc.detail))


# --- helpers -----------------------------------------------------------------------------------

def _snapshot(request: Request, thread_id: str):
    """The latest checkpoint of a session; 404 if there is none and no run is starting it."""
    snapshot = request.app.state.graph.get_state(graph_config(thread_id))
    if not snapshot.values and not request.app.state.runner.is_running(thread_id):
        raise ApiError(404, "not_found", f"No session with thread_id {thread_id}.")
    return snapshot


def _run_state(runner: GraphRunner, thread_id: str, snapshot) -> str:
    if runner.is_running(thread_id):
        return "running"
    if snapshot.interrupts:
        return "paused"
    if snapshot.next:              # nodes still to run, but nobody is running them: restart or crash
        return "interrupted"
    return "finished"


def _counters(values: dict) -> Counters:
    research_passes = values.get("research_retry_count", 0) + (1 if values.get("research_queries") else 0)
    return Counters(
        clarification_rounds=values.get("clarification_round_count", 0),
        research_passes=research_passes,
        debate_round=values.get("debate_round", 0),
        evidence=len(values.get("evidence", [])),
        proposals=len(values.get("proposals", [])),
        claims_checked=len(values.get("verification_results", [])),
    )


def _start(runner: GraphRunner, thread_id: str, graph_input) -> None:
    if not runner.start(thread_id, graph_input):
        raise ApiError(409, "already_running", "This session is still running; wait until it pauses or finishes.")


# --- endpoints ---------------------------------------------------------------------------------

@app.post("/api/decisions", status_code=status.HTTP_202_ACCEPTED, response_model=Accepted, tags=["decisions"])
def create_decision(body: CreateDecisionRequest, request: Request,
                    x_user_id: Annotated[str | None, Header(description="Anonymous browser id (long-term memory).")] = None):
    """Create a session and start the graph in the background. Returns at once with the thread_id.
    With an X-User-Id header, what we remember about this patient goes into the session (memory.py)."""
    thread_id = str(uuid.uuid4())
    user_id = valid_user_id(x_user_id) or ""
    if get_settings().persist_results:
        save_session_status(thread_id, {"question": body.question, "mode": body.mode, "user_id": user_id}, "intake")
    _start(request.app.state.runner, thread_id, {"question": body.question, "user_context": body.context, "mode": body.mode,
                                                 "user_id": user_id, "user_memories": memory.load(user_id)})
    return Accepted(thread_id=thread_id)


@app.get("/api/decisions", response_model=SessionList, tags=["decisions"])
def list_decisions(limit: int = 20, mode: Literal["full", "quick"] | None = None):
    """Recent sessions, newest first (from decision_sessions, so only sessions saved with PERSIST_RESULTS=true).
    mode=quick lists only patient chats, mode=full only admin sessions; no mode lists all."""
    try:
        rows = list_sessions(limit=max(1, min(limit, 100)), mode=mode)
    except Exception as exc:                        # noqa: BLE001 - the list is a convenience; sessions still work by URL
        logging.getLogger(__name__).exception("could not list sessions")
        raise ApiError(503, "database_unavailable", f"Could not read the session list: {type(exc).__name__}.") from exc
    return SessionList(sessions=[
        SessionSummary(
            thread_id=r.thread_id,
            question=r.question,
            mode=r.mode,
            project_name=r.project_name,
            status=r.status,
            risk_flag_count=len(r.risk_flags or []),
            created_at=r.created_at.isoformat(timespec="seconds"),
            updated_at=r.updated_at.isoformat(timespec="seconds") if r.updated_at else None,
            completed_at=r.completed_at.isoformat(timespec="seconds") if r.completed_at else None,
        )
        for r in rows
    ])


@app.get("/api/decisions/{thread_id}", response_model=DecisionStatus, tags=["decisions"])
def get_decision(thread_id: str, request: Request):
    """Poll this every couple of seconds. When run_state is "paused", `pending` says what to send to /resume."""
    runner: GraphRunner = request.app.state.runner
    snapshot = _snapshot(request, thread_id)
    values = snapshot.values or {}
    run_state = _run_state(runner, thread_id, snapshot)

    pending = None
    if run_state == "paused":
        payload = snapshot.interrupts[0].value
        pending = PendingPause(type=payload["type"], payload=payload)

    error = None
    if runner.crash(thread_id):
        error = {"code": "run_crashed", "message": runner.crash(thread_id)}
    elif values.get("error"):
        err = values["error"]
        error = {"code": err.get("category", "error"), "message": f"{err.get('node', '?')}: {err.get('message', '')}"}

    return DecisionStatus(
        thread_id=thread_id,
        run_state=run_state,
        workflow_status=values.get("status"),
        question=values.get("question"),
        project_name=values.get("project_name"),
        risk_flags=values.get("risk_flags", []),
        pending=pending,
        progress=runner.progress(thread_id),
        error=error,
        has_report=bool(values.get("final_report")),
        has_brief=_validated_brief(values) is not None,
        has_plan=bool(values.get("implementation_plan")),
        current_node=values.get("current_node"),
        next_nodes=list(snapshot.next or ()),
        started_at=values.get("started_at"),
        active_seconds=float(values.get("active_seconds", 0.0) or 0.0),
        counters=_counters(values),
    )


@app.post("/api/decisions/{thread_id}/resume", status_code=status.HTTP_202_ACCEPTED, response_model=Accepted,
          tags=["decisions"])
def resume_decision(thread_id: str, body: ResumeRequest, request: Request):
    """Answer the pending pause. `type` must match pending.type from GET; {"type": "continue"} restarts an
    interrupted run. The graph continues in the background; poll GET again."""
    runner: GraphRunner = request.app.state.runner
    snapshot = _snapshot(request, thread_id)
    run_state = _run_state(runner, thread_id, snapshot)

    if run_state == "running":
        raise ApiError(409, "already_running", "This session is still running; wait until it pauses or finishes.")
    if isinstance(body, ContinueResume):
        if run_state != "interrupted":
            raise ApiError(409, "not_interrupted", f"Nothing to continue: the session is {run_state}.")
        _start(runner, thread_id, None)            # None = continue from the last checkpoint
        return Accepted(thread_id=thread_id)
    if run_state != "paused":
        raise ApiError(409, "nothing_pending", f"The session is not waiting for input (it is {run_state}).")

    payload = snapshot.interrupts[0].value
    if body.type != payload["type"]:
        raise ApiError(409, "wrong_pause_type", f"The session is waiting for '{payload['type']}', not '{body.type}'.")

    # Checks the graph would also make (it re-asks with an error); doing them here gives a direct 422.
    if isinstance(body, ClarificationResume):
        unknown = sorted(set(body.answers) - set(payload["questions"]))
        if unknown:
            raise ApiError(422, "invalid_input", f"Answers for questions that were not asked: {unknown}")

    if isinstance(body, BriefReviewResume):
        if body.action == "request_changes" and len(body.feedback.strip()) < 3:
            raise ApiError(422, "invalid_input", "Describe the change you want: feedback is required to request changes.")
        if body.action == "request_changes" and payload.get("wording_only") and body.target not in ("auto", "wording"):
            raise ApiError(422, "invalid_input", "The brief was revised the maximum number of times: only wording changes "
                                                 "(or approval) are accepted now.")

    if isinstance(body, PlanReviewResume):
        if body.action == "request_changes" and len(body.feedback.strip()) < 3:
            raise ApiError(422, "invalid_input", "Describe the change you want: feedback is required to request changes.")
        if body.action == "request_changes" and not payload.get("changes_allowed", True):
            raise ApiError(422, "invalid_input", "The plan was revised the maximum number of times: it can only be approved now.")

    reply = body.model_dump(exclude={"type"})      # exactly what interrupt() returns inside the node
    _start(runner, thread_id, Command(resume=reply))
    return Accepted(thread_id=thread_id)


@app.get("/api/decisions/{thread_id}/report", response_model=ReportResponse, tags=["decisions"])
def get_report(thread_id: str, request: Request):
    snapshot = _snapshot(request, thread_id)
    run_state = _run_state(request.app.state.runner, thread_id, snapshot)
    if run_state != "finished":
        raise ApiError(409, "not_finished", f"Not finished yet (the session is {run_state}).")
    values = snapshot.values
    if not values.get("final_report"):
        raise ApiError(409, "no_report", f"This session ended without a report (status {values.get('status')}).")
    return ReportResponse(thread_id=thread_id, workflow_status=values.get("status"), report=values["final_report"])


def _validated_brief(values: dict) -> tuple[dict, dict] | None:
    """(brief, validation) when the current draft passed the validator (approve), else None."""
    brief, validation = values.get("brief"), values.get("brief_validation")
    if not brief or not validation or validation.get("verdict") != "approve":
        return None
    if validation.get("brief_generated_at") != brief.get("generated_at"):
        return None                               # the validation belongs to an earlier draft
    return brief, validation


@app.get("/api/decisions/{thread_id}/brief", response_model=BriefResponse, tags=["decisions"])
def get_brief(thread_id: str, request: Request):
    """The problem statement + solution brief, once the validator approved the current draft (also while the graph
    is paused or still running later steps). 409 "no_brief" before that: an unvalidated draft is never shown."""
    values = _snapshot(request, thread_id).values or {}
    found = _validated_brief(values)
    if not found:
        raise ApiError(409, "no_brief", f"No validated brief yet (status {values.get('status')}).")
    brief, validation = found
    return BriefResponse(thread_id=thread_id, workflow_status=values.get("status"), brief=brief,
                         markdown=values.get("brief_markdown", ""), validation=validation,
                         approved_at=values.get("brief_approved_at") if brief_is_approved(values) else None,
                         review_round=values.get("brief_review_round_count", 0))


@app.get("/api/decisions/{thread_id}/plan", response_model=PlanResponse, tags=["decisions"])
def get_plan(thread_id: str, request: Request):
    """The implementation plan once the planner wrote one (409 "no_plan" before)."""
    values = _snapshot(request, thread_id).values or {}
    plan = values.get("implementation_plan")
    if not plan:
        raise ApiError(409, "no_plan", f"No implementation plan yet (status {values.get('status')}).")
    return PlanResponse(thread_id=thread_id, workflow_status=values.get("status"), plan=plan,
                        markdown=values.get("plan_markdown", ""), revision=values.get("plan_revision_count", 0),
                        model=(values.get("models_used") or {}).get("planner", ""),
                        approved_at=values.get("plan_approved_at") if plan_is_approved(values) else None,
                        tasks=values.get("implementation_tasks", []))


@app.get("/api/decisions/{thread_id}/artifacts", response_model=ArtifactList, tags=["decisions"])
def get_artifacts(thread_id: str, request: Request):
    """Approved versions (project_artifacts table). 503 if the database cannot be read."""
    _snapshot(request, thread_id)                       # 404 for unknown sessions
    try:
        rows = list_artifacts(thread_id)
    except Exception as exc:
        raise ApiError(503, "database_unavailable", f"Could not read the artifacts ({type(exc).__name__}).") from exc
    return ArtifactList(thread_id=thread_id, artifacts=[
        ArtifactView(kind=r.kind, version=r.version, content_hash=r.content_hash, markdown=r.markdown,
                     approved_at=r.approved_at.isoformat() if r.approved_at else None, created_at=r.created_at.isoformat())
        for r in rows])


@app.get("/api/decisions/{thread_id}/evidence", response_model=EvidenceResponse, tags=["decisions"])
def get_evidence(thread_id: str, request: Request):
    """Evidence kept so far (also while running). verification_status stays "pending" until the Evidence Checker ran."""
    evidence = (_snapshot(request, thread_id).values or {}).get("evidence", [])
    counts = Counter(e.get("verification_status", "pending") for e in evidence)
    return EvidenceResponse(thread_id=thread_id, count=len(evidence), verification_counts=dict(counts), evidence=evidence)


@app.get("/api/decisions/{thread_id}/live", response_model=LiveSnapshot, tags=["decisions"])
def get_live(thread_id: str, request: Request):
    """Everything the agents produced so far (case facts, evidence counts, plans, criticisms, scores, verdicts).
    Readable at any time; the frontend fetches it whenever a node finishes, so the user can watch the work appear."""
    snapshot = _snapshot(request, thread_id)
    values = snapshot.values or {}
    evidence = values.get("evidence", [])
    by_perspective = Counter(e.get("domain", "?") for e in evidence)
    return LiveSnapshot(
        thread_id=thread_id,
        run_state=_run_state(request.app.state.runner, thread_id, snapshot),
        workflow_status=values.get("status"),
        current_node=values.get("current_node"),
        case=CaseView(
            project_name=values.get("project_name"),
            project_category=values.get("project_category"),
            idea_summary=values.get("idea_summary"),
            user_context=values.get("user_context") or "",
            project_profile=values.get("project_profile", {}),
            requested_features=values.get("requested_features", {}),
            constraints=values.get("constraints", {}),
            missing_information=values.get("missing_information", []),
            assumptions=values.get("assumptions", []),
            clarification_answers=values.get("clarification_answers", {}),
            risk_flags=values.get("risk_flags", []),
            withdrawn_risk_flags=values.get("withdrawn_risk_flags", []),
        ),
        research=ResearchView(
            passes=_counters(values).research_passes,
            queries=values.get("research_queries", []),
            evidence_by_domain=dict(by_perspective),
            evidence_gaps=values.get("evidence_gaps", []),
            conflicting_claims=values.get("conflicting_claims", []),
            rejected_count=len(values.get("rejected_sources", [])),
            domain_summaries=values.get("domain_summaries", {}),
            research_focus=values.get("research_focus", []),
        ),
        debate=DebateView(
            round=values.get("debate_round", 0),
            proposals=values.get("proposals", []),
            criticisms=values.get("criticisms", []),
            scores=values.get("scores", []),
            verdict=values.get("verdict") or None,
            proposer_status=values.get("proposer_status", ""),
            proposer_notes=values.get("proposer_notes", "") or "",
        ),
        verification=VerificationView(
            results=values.get("verification_results", []),
            verdict=values.get("checker_verdict") or None,
            unresolved_questions=values.get("unresolved_questions", []),
        ),
        metrics=values.get("metrics") or None,
    )
