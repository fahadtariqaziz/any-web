"""FastAPI backend: the same flow as scripts/run_graph.py, over HTTP (for the Next.js frontend).

Run from the backend/ folder:
    uv run uvicorn ai_decision_arena.api.main:app --port 8000
Then open http://localhost:8000/docs (Swagger UI: try every endpoint from the browser).

Flow:
    POST /api/decisions                   → 202 {thread_id}; the graph runs in the background
    GET  /api/decisions/{id}              → poll every ~2 s: run_state, progress lines, pending pause
    POST /api/decisions/{id}/resume       → answer the pending pause ("continue" an interrupted run, "reopen" a finished one)
    POST /api/decisions/{id}/cancel       → stop a running session after its current step (then "continue" resumes it)
    GET  /api/decisions/{id}/report       → the final report, once finished
    GET  /api/decisions/{id}/brief        → the validated problem statement + solution brief
    GET  /api/decisions/{id}/plan         → the implementation plan (from the plan review on)
    GET  /api/decisions/{id}/artifacts    → approved versions of the brief and the plan
    GET  /api/decisions/{id}/implementation → the coding agent's tasks, attempt log and last build check
    GET  /api/decisions/{id}/preview      → the live preview (dev server) state; POST .../preview/restart | stop
    GET  /api/decisions/{id}/code         → the generated project's files (JSON, base64) for "Download code"; /code.zip
    GET  /api/decisions/{id}/evidence     → kept evidence with verification status
    GET  /api/decisions/{id}/live         → everything produced so far (case, evidence counts, plans, scores, verdicts)
    GET  /api/decisions                   → recent sessions (from the app tables)
    GET  /api/chats/{id}                  → the builder conversation (api/chat.py)
    POST /api/chats/{id}/messages         → an Ask-mode question; the reply streams back as text (api/chat.py)
    GET / DELETE /api/memories            → what the agents remember about this browser's user (api/memories.py)
    GET  /api/decisions/{id}/usage        → what the session cost (builder AI + coding agent), per stage / change / step
    GET  /api/decisions/{id}/tool-calls   → the session's tool calls (agent decisions, commands, Ask tools, searches)
    GET  /api/metrics                     → usage, tool failures and costs across sessions
    GET  /api/triggers                    → the trigger table; POST /api/triggers/idle-previews stops idle previews now

Status and pending pause are read from the checkpoint (graph.get_state), so they survive a restart.
"""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from collections import Counter
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_decision_arena import memory, usage
from ai_decision_arena.pricing import PRICES_AS_OF
from ai_decision_arena.api.chat import router as chat_router
from ai_decision_arena.api.memories import router as memories_router
from ai_decision_arena.api.runner import GraphRunner, graph_config
from ai_decision_arena.api.triggers import router as triggers_router
from ai_decision_arena.api.errors import ApiError
from ai_decision_arena.api.schemas import (
    Accepted,
    CancelAccepted,
    ChangeRequestResume,
    CodeExportResponse,
    ImplementationResponse,
    MetricsResponse,
    ToolCallList,
    ToolCallView,
    UsageResponse,
    AppSettingsResponse,
    AppSettingsUpdate,
    DatabaseSetupRequest,
    PreviewResponse,
    ReopenResume,
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
from ai_decision_arena.db.repository import (agent_cost_since, list_artifacts, list_sessions, save_session_status,
                                             list_tool_calls, session_node_cost, tool_metrics, usage_metrics)
from ai_decision_arena.graph import build_graph
from ai_decision_arena.llm import resolve_model
from ai_decision_arena.memory import valid_user_id
from ai_decision_arena.nodes.delivery import reopen_actions, reopen_update
from ai_decision_arena.workspace import app_settings, export as code_export, render_check, supabase_setup
from ai_decision_arena.workspace.paths import PathError, workspace_for
from ai_decision_arena.workspace.processes import IdleStopper, RuntimeRecord, get_manager

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
    app.state.processes = get_manager()           # shared with the preview node (graph threads)
    app.state.processes.reconcile()
    idle_stopper = IdleStopper(app.state.processes)
    idle_stopper.start()
    yield
    idle_stopper.stop()
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


def display_name(values: dict) -> str | None:
    """The project's name for headers: the brief's proposed name once there is one (the brief may rename the idea
    intake named, e.g. "simple calculator web app" -> "Simple calculator web app"), else intake's project_name."""
    proposed = ((values.get("brief") or {}).get("project_overview") or {}).get("proposed_name", "").strip()
    return proposed or values.get("project_name")


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
    With an X-User-Id header, what we remember about this user goes into the session (memory.py)."""
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
    mode=full / mode=quick (legacy health-app chats) filters; no mode lists all."""
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
        project_name=display_name(values),
        risk_flags=values.get("risk_flags", []),
        pending=pending,
        progress=runner.progress(thread_id),
        error=error,
        has_report=bool(values.get("final_report")),
        has_brief=_validated_brief(values) is not None,
        has_draft_brief=_draft_brief(values) is not None,
        has_plan=bool(values.get("implementation_plan")),
        has_build=bool(values.get("workspace_dir")),
        reopen_actions=reopen_actions(values) if run_state == "finished" else [],
        current_node=values.get("current_node"),
        next_nodes=list(snapshot.next or ()),
        started_at=values.get("started_at"),
        active_seconds=float(values.get("active_seconds", 0.0) or 0.0),
        counters=_counters(values),
        cancelled=run_state == "interrupted" and runner.cancelled(thread_id),
    )


@app.post("/api/decisions/{thread_id}/cancel", status_code=status.HTTP_202_ACCEPTED, response_model=CancelAccepted,
          tags=["decisions"])
def cancel_decision(thread_id: str, request: Request):
    """Stop a running session safely (review 2026-10-29): the step in progress finishes and is checkpointed, no
    later step starts, and the session waits as "interrupted" with cancelled=true until {"type": "continue"}.
    409 "not_running" when nothing is running."""
    runner: GraphRunner = request.app.state.runner
    _snapshot(request, thread_id)                      # 404 for an unknown session
    if not runner.cancel(thread_id):
        raise ApiError(409, "not_running", "Nothing to stop: the session is not running.")
    return CancelAccepted(thread_id=thread_id)


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
    if isinstance(body, ReopenResume):
        if run_state != "finished":
            raise ApiError(409, "not_finished", f"Only a finished project can be reopened (it is {run_state}).")
        allowed = reopen_actions(snapshot.values or {})
        if body.action not in allowed:
            reason = ("the maximum number of change requests or plan revisions was reached" if allowed or
                      (snapshot.values or {}).get("change_requests") else "it was not built and finished in the builder")
            raise ApiError(422, "invalid_input", f"This project cannot take a {body.action} any more: {reason}.")
        config = graph_config(thread_id)
        request.app.state.graph.update_state(config, reopen_update(snapshot.values, body.action, body.request),
                                             as_node="await_change_request")
        _start(runner, thread_id, None)            # continues at change_request_router
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
            raise ApiError(422, "invalid_input", "Your app is already built: changes to the brief are edits (wording) only."
                           if payload.get("wording_only_reason") == "built" else
                           "The brief was revised the maximum number of times: only wording changes (or approval) are "
                           "accepted now.")

    if isinstance(body, PlanReviewResume):
        if body.action == "request_changes" and len(body.feedback.strip()) < 3:
            raise ApiError(422, "invalid_input", "Describe the change you want: feedback is required to request changes.")
        if body.action == "request_changes" and not payload.get("changes_allowed", True):
            raise ApiError(422, "invalid_input", "The plan was revised the maximum number of times: it can only be approved now.")

    if isinstance(body, ChangeRequestResume):
        if body.action != "finish" and len(body.request.strip()) < 3:
            raise ApiError(422, "invalid_input", "Describe the change you want: a request is required.")
        if body.action != "finish" and not payload.get("changes_allowed", True):
            raise ApiError(422, "invalid_input", "The maximum number of change requests was reached: finish the session.")
        if body.action == "replan" and not payload.get("replan_allowed", True):
            raise ApiError(422, "invalid_input", "The plan was revised the maximum number of times: ask for a change instead.")

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


def _draft_brief(values: dict) -> dict | None:
    """The draft the validator is checking right now (status validating_brief), when no validated version of it exists."""
    if values.get("status") != "validating_brief" or not values.get("brief") or _validated_brief(values):
        return None
    return values["brief"]


@app.get("/api/decisions/{thread_id}/brief", response_model=BriefResponse, tags=["decisions"])
def get_brief(thread_id: str, request: Request):
    """The problem statement + solution brief, once the validator approved the current draft (also while the graph
    is paused or still running later steps). While the validator checks a draft, that draft with is_draft=true and
    no validation (speed: readable ~15 s earlier, clearly marked). 409 "no_brief" otherwise."""
    values = _snapshot(request, thread_id).values or {}
    found = _validated_brief(values)
    if not found:
        draft = _draft_brief(values)
        if draft is None:
            raise ApiError(409, "no_brief", f"No validated brief yet (status {values.get('status')}).")
        return BriefResponse(thread_id=thread_id, workflow_status=values.get("status"), brief=draft,
                             markdown=values.get("brief_markdown", ""), validation=None, is_draft=True,
                             review_round=values.get("brief_review_round_count", 0))
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


@app.get("/api/decisions/{thread_id}/implementation", response_model=ImplementationResponse, tags=["decisions"])
def get_implementation(thread_id: str, request: Request):
    """The coding agent's tasks and log (409 "no_implementation" before the plan was approved)."""
    values = _snapshot(request, thread_id).values or {}
    if not values.get("workspace_dir"):
        raise ApiError(409, "no_implementation", f"Nothing built yet (status {values.get('status')}).")
    return ImplementationResponse(thread_id=thread_id, workflow_status=values.get("status"),
                                  workspace_dir=values.get("workspace_dir"), current_task_id=values.get("current_task_id"),
                                  tasks=values.get("implementation_tasks", []), log=values.get("implementation_log", []),
                                  cost_usd=values.get("implementation_cost_usd", 0.0), build=values.get("build_results"),
                                  e2e=values.get("e2e_results"), review=values.get("code_review"),
                                  learnings=values.get("learnings") or [])


@app.get("/api/decisions/{thread_id}/usage", response_model=UsageResponse, tags=["decisions"])
def get_usage(thread_id: str, request: Request):
    """What the session cost so far: the builder's model calls + the coding agent, per phase / change / step."""
    snapshot = _snapshot(request, thread_id)
    values = snapshot.values or {}
    settings = get_settings()
    ask_usd = None
    if settings.persist_results:
        try:
            ask_usd = session_node_cost(thread_id, "ask")
        except Exception:                           # noqa: BLE001 - the rest of the report still holds
            logging.getLogger(__name__).exception("could not read Ask usage")
    return UsageResponse(thread_id=thread_id, ask_usd=ask_usd, llm_budget_usd=settings.session_llm_budget_usd,
                         agent_budget_usd=settings.implementation_budget_usd, prices_as_of=PRICES_AS_OF,
                         **usage.session_cost(values))


@app.get("/api/metrics", response_model=MetricsResponse, tags=["metrics"])
def get_metrics(days: int = 7):
    """The builder's model usage over the last `days` days (usage_events, written since M11): totals, per node,
    per day, calls per model, node failures; plus the coding agent's spend from completed sessions."""
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        data = usage_metrics(since)
        agent = agent_cost_since(since)
        tools = tool_metrics(since)
    except Exception as exc:                        # noqa: BLE001
        logging.getLogger(__name__).exception("could not read metrics")
        raise ApiError(503, "database_unavailable", f"Could not read the metrics: {type(exc).__name__}.") from exc
    return MetricsResponse(since=since.isoformat(timespec="seconds"), days=days, agent=agent, tools=tools, **data)


@app.get("/api/decisions/{thread_id}/tool-calls", response_model=ToolCallList, tags=["decisions"])
def get_tool_calls(thread_id: str, request: Request, limit: int = 300,
                   source: Literal["agent", "sandbox", "chat", "search"] | None = None):
    """The session's tool calls (agent tool decisions, sandbox commands, Ask tools, searches), newest first."""
    _snapshot(request, thread_id)                   # 404 for an unknown session
    if not get_settings().persist_results:
        return ToolCallList(thread_id=thread_id, calls=[])
    try:
        rows = list_tool_calls(thread_id, limit=max(1, min(limit, 2000)), source=source)
    except Exception as exc:                        # noqa: BLE001
        logging.getLogger(__name__).exception("could not read tool calls")
        raise ApiError(503, "database_unavailable", f"Could not read the tool calls: {type(exc).__name__}.") from exc
    calls = [ToolCallView(source=r.source, tool=r.tool, target=r.target, label=r.label, ok=r.ok, reason=r.reason,
                          exit_code=r.exit_code, timed_out=r.timed_out, duration_seconds=r.duration_seconds,
                          at=r.at.isoformat(timespec="seconds")) for r in rows]
    return ToolCallList(thread_id=thread_id, calls=calls, counts={
        "total": len(calls), "failed": sum(not c.ok for c in calls),
        "denied_or_refused": sum(not c.ok and c.exit_code is None and not c.timed_out for c in calls)})


def _preview_response(thread_id: str, record: RuntimeRecord) -> PreviewResponse:
    return PreviewResponse(thread_id=thread_id, state=record.state, url=record.url if record.state == "ready" else None,
                           port=record.port, command=record.command, last_error=record.last_error,
                           log_tail=get_manager().log_tail(thread_id)[-3000:],
                           started_at=record.started_at.isoformat() if record.started_at else None,
                           ready_at=record.ready_at.isoformat() if record.ready_at else None,
                           render=_render(thread_id, record))


def _render(thread_id: str, record: RuntimeRecord) -> dict | None:
    if record.state != "ready":
        return None
    try:
        return render_check.load(workspace_for(thread_id), record.started_at)
    except PathError:
        return None


def _preview_record(request: Request, thread_id: str) -> RuntimeRecord:
    _snapshot(request, thread_id)                                   # 404 for unknown sessions
    try:
        record = get_manager().status(thread_id)
    except Exception as exc:
        raise ApiError(503, "database_unavailable", f"Could not read the preview ({type(exc).__name__}).") from exc
    if record is None:
        raise ApiError(409, "no_preview", "This session has no preview yet.")
    return record


@app.get("/api/decisions/{thread_id}/preview", response_model=PreviewResponse, tags=["preview"])
def get_preview(thread_id: str, request: Request):
    """Live state of the session's dev server. Reading it counts as "looked at" for the idle stop."""
    record = _preview_record(request, thread_id)
    get_manager().touch(thread_id)
    return _preview_response(thread_id, record)


@app.post("/api/decisions/{thread_id}/preview/restart", response_model=PreviewResponse, tags=["preview"])
def restart_preview(thread_id: str, request: Request):
    """Restart the dev server with the approved plan's dev command; returns after the health check (≤ 60 s)."""
    values = _snapshot(request, thread_id).values or {}
    plan = values.get("implementation_plan")
    if not plan or not values.get("workspace_dir"):
        raise ApiError(409, "no_preview", "This session has nothing to preview yet.")
    if _run_state(request.app.state.runner, thread_id, _snapshot(request, thread_id)) == "running":
        raise ApiError(409, "already_running", "The builder is working on this session; the preview restarts itself.")
    try:
        ws = workspace_for(thread_id)
    except PathError as exc:
        raise ApiError(422, "invalid_input", str(exc)) from exc
    record = get_manager().start(ws, plan["commands"]["dev"])
    render_check.check_preview(ws, record)                  # the pane shows a blank page's browser errors
    return _preview_response(thread_id, record)


def _app_settings_ws(request: Request, thread_id: str):
    values = _snapshot(request, thread_id).values or {}            # 404 for unknown sessions
    if not values.get("workspace_dir"):
        raise ApiError(409, "no_implementation", "Nothing built yet: the app has no settings.")
    try:
        return workspace_for(thread_id), values
    except PathError as exc:
        raise ApiError(422, "invalid_input", str(exc)) from exc


def _without_url(check: dict | None) -> dict | None:
    return {k: v for k, v in check.items() if k != "url"} if check else None      # the API never echoes a value


def _settings_response(thread_id: str, ws, **extra) -> AppSettingsResponse:
    database = None
    if supabase_setup.applies(ws):
        database = {"migrations": [p.name for p in supabase_setup.migration_files(ws)],
                    "tables": supabase_setup.tables(ws), "check": _without_url(supabase_setup.last_check(ws))}
        database |= {"setup": extra.pop("setup")} if "setup" in extra else {}
    return AppSettingsResponse(thread_id=thread_id, database=database, **extra, **app_settings.describe(ws))


@app.get("/api/decisions/{thread_id}/app-settings", response_model=AppSettingsResponse, tags=["preview"])
def get_app_settings(thread_id: str, request: Request):
    """The variables of the app's .env.example: set or missing, with setup steps. Never returns a value."""
    ws, _ = _app_settings_ws(request, thread_id)
    return _settings_response(thread_id, ws)


@app.post("/api/decisions/{thread_id}/app-settings/database/check", response_model=AppSettingsResponse, tags=["preview"])
def check_app_database(thread_id: str, request: Request):
    """Read-only: do the tables of the app's Supabase migrations exist in the user's project?"""
    ws, _ = _app_settings_ws(request, thread_id)
    if not supabase_setup.applies(ws):
        raise ApiError(409, "no_database", "This app has no Supabase migrations.")
    supabase_setup.check(ws)
    return _settings_response(thread_id, ws)


@app.post("/api/decisions/{thread_id}/app-settings/database/setup", response_model=AppSettingsResponse, tags=["preview"])
def setup_app_database(thread_id: str, body: DatabaseSetupRequest, request: Request):
    """Writes to the USER's database, only on their request: runs the migration files not applied yet (one
    transaction each), then checks again. The connection string is used for this call only."""
    ws, _ = _app_settings_ws(request, thread_id)
    if not supabase_setup.applies(ws):
        raise ApiError(409, "no_database", "This app has no Supabase migrations.")
    result = supabase_setup.apply(ws, body.db_url)
    if result["files"]:
        supabase_setup.check(ws)
    return _settings_response(thread_id, ws, setup=result)


@app.put("/api/decisions/{thread_id}/app-settings", response_model=AppSettingsResponse, tags=["preview"])
def put_app_settings(thread_id: str, body: AppSettingsUpdate, request: Request):
    """Save settings for the preview (outside the code), then restart the preview with them unless the builder is
    working on the session (its next preview start uses them)."""
    ws, values = _app_settings_ws(request, thread_id)
    problems = app_settings.save(ws, body.values)
    if problems:
        raise ApiError(422, "invalid_input", "; ".join(problems))
    preview = None
    plan = values.get("implementation_plan")
    if plan and _run_state(request.app.state.runner, thread_id, _snapshot(request, thread_id)) != "running":
        record = get_manager().start(ws, plan["commands"]["dev"])
        render_check.check_preview(ws, record)
        preview = _preview_response(thread_id, record)
    if supabase_setup.applies(ws):
        supabase_setup.check(ws)                                    # read-only: are the app's tables there?
    return _settings_response(thread_id, ws, preview=preview)


@app.post("/api/decisions/{thread_id}/preview/stop", response_model=PreviewResponse, tags=["preview"])
def stop_preview(thread_id: str, request: Request):
    _preview_record(request, thread_id)
    return _preview_response(thread_id, get_manager().stop(thread_id, reason="user"))


def _code_export(request: Request, thread_id: str) -> code_export.CodeExport:
    values = _snapshot(request, thread_id).values or {}
    if not values.get("workspace_dir"):
        raise ApiError(409, "no_implementation", "Nothing built yet: there is no code to download.")
    try:
        return code_export.collect(workspace_for(thread_id), values.get("project_name"))
    except PathError as exc:
        raise ApiError(422, "invalid_input", str(exc)) from exc


@app.get("/api/decisions/{thread_id}/code", response_model=CodeExportResponse, tags=["preview"])
def get_code(thread_id: str, request: Request):
    """The project's files as JSON (base64), for the browser to write into a folder the user picks."""
    return CodeExportResponse(thread_id=thread_id, **code_export.as_json(_code_export(request, thread_id)))


@app.get("/api/decisions/{thread_id}/code.zip", tags=["preview"])
def get_code_zip(thread_id: str, request: Request):
    """The same files as a zip with one top-level folder (browsers without a folder picker)."""
    export = _code_export(request, thread_id)
    return Response(content=code_export.as_zip(export), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{export.folder_name}.zip"'})


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
    """Evidence kept so far (also while running). verification_status stays "pending" until the Judge consolidated the winner's claim check."""
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
