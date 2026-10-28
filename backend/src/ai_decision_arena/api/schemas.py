"""Request and response models of the HTTP API.

FastAPI validates every request body against these BEFORE our code runs: a malformed body gets a
422 with a clear message, and the Swagger page (/docs) shows each model with its fields.

The resume body is a "discriminated union": the `type` field says which pause you are answering,
and FastAPI picks the matching model (ClarificationResume, BriefReviewResume, PlanReviewResume, ContinueResume).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_decision_arena.nodes.intake import MAX_CONTEXT_CHARS, MAX_QUESTION_CHARS, MIN_QUESTION_CHARS
from ai_decision_arena.schemas import (
    ClaimVerification,
    Criticism,
    Evidence,
    BriefValidation,
    FinalReport,
    ImplementationPlan,
    ProblemBrief,
    ProposalScore,
    SolutionProposal,
    Verdict,
)

# What the HTTP layer knows about a session (separate from the graph's own `status` field):
# running     a background run is working on it right now
# paused      waiting for the user (see `pending`)
# interrupted the run stopped mid-way (server restart, crash); POST /resume {"type": "continue"} picks it up
# finished    the graph reached END (completed or failed: see workflow_status)
RunState = Literal["running", "paused", "interrupted", "finished"]
PauseType = Literal["clarification", "brief_review", "plan_review", "change_request"]


# --- requests ----------------------------------------------------------------------------------

class CreateDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)   # "   " counts as empty, like in intake

    question: str = Field(min_length=MIN_QUESTION_CHARS, max_length=MAX_QUESTION_CHARS,
                          examples=["A habit tracker app for university students"])
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS, description="Optional extra context.")
    mode: Literal["full"] = Field(default="full", description='Always "full": every agent, every loop (the quick '
                                  "profile was retired in M11; old sessions may still say quick).")


class ClarificationResume(BaseModel):
    type: Literal["clarification"]
    answers: dict[str, str] = Field(description="question -> answer, using the exact question texts from `pending`. "
                                                "Leave a question out (or answer \"\") to skip it.")


class BriefReviewResume(BaseModel):
    """Approve the brief, or ask for changes (feedback required). target: where the change should go; "auto" lets the
    system decide. After max_review_rounds change requests, only "wording" / "auto" are accepted."""

    type: Literal["brief_review"]
    action: Literal["approve", "request_changes"]
    feedback: str = Field(default="", max_length=4000)
    target: Literal["auto", "requirements", "research", "proposal", "wording"] = "auto"


class PlanReviewResume(BaseModel):
    """Approve the implementation plan, or ask for changes (feedback required; refused after max_plan_revisions)."""

    type: Literal["plan_review"]
    action: Literal["approve", "request_changes"]
    feedback: str = Field(default="", max_length=4000)


class ChangeRequestResume(BaseModel):
    """While the preview runs: a change for the coding agent, a new plan (approved again), or finish the session.
    `request` is required for change / replan; refused once max_change_requests is reached."""

    type: Literal["change_request"]
    action: Literal["change", "replan", "finish"]
    request: str = Field(default="", max_length=4000)


class ReopenResume(BaseModel):
    """A FINISHED project takes another change (or a new plan): it reopens at the change-request step (M10). Allowed
    while DecisionStatus.reopen_actions lists the action (same limits as the change-request pause)."""

    type: Literal["reopen"]
    action: Literal["change", "replan"]
    request: str = Field(min_length=3, max_length=4000)


class ContinueResume(BaseModel):
    """Restart an interrupted run from its last checkpoint (like run_graph.py --resume)."""

    type: Literal["continue"]


ResumeRequest = Annotated[
    ClarificationResume | BriefReviewResume | PlanReviewResume | ChangeRequestResume | ReopenResume | ContinueResume,
    Field(discriminator="type"),
]


# --- responses ---------------------------------------------------------------------------------

class Accepted(BaseModel):
    thread_id: str
    run_state: RunState = "running"
    message: str = "Accepted. Poll GET /api/decisions/{thread_id} for progress."


class CancelAccepted(BaseModel):
    thread_id: str
    message: str = "Stopping after the current step; the session then waits for {\"type\": \"continue\"}."


class ProgressLine(BaseModel):
    at: str
    node: str
    message: str


class PendingPause(BaseModel):
    type: PauseType
    payload: dict[str, Any] = Field(description="Exactly what the graph's interrupt() sent: the questions. "
                                                "Includes `error` if the last reply was refused.")


class ErrorInfo(BaseModel):
    code: str
    message: str


class Counters(BaseModel):
    """Small numbers the frontend shows next to the pipeline (all read from the checkpoint)."""

    clarification_rounds: int = 0
    research_passes: int = 0        # first pass + retries (0 until research ran)
    debate_round: int = 0
    evidence: int = 0
    proposals: int = 0
    claims_checked: int = 0


class DecisionStatus(BaseModel):
    thread_id: str
    run_state: RunState
    workflow_status: str | None = Field(description="The graph's own status (intake, researching, completed, ...).")
    question: str | None = None
    project_name: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    pending: PendingPause | None = None
    progress: list[ProgressLine] = Field(default_factory=list,
                                         description="Live progress of THIS server process (lost on restart).")
    error: ErrorInfo | None = Field(default=None, description="The graph's stored error, or a crash of the background run.")
    has_report: bool = False
    has_brief: bool = Field(default=False, description="True once a validated brief exists (GET /brief).")
    has_draft_brief: bool = Field(default=False, description="True while the validator checks a fresh draft: GET /brief "
                                  "returns it with is_draft=true (shown early, marked as being checked).")
    has_plan: bool = Field(default=False, description="True once the planner wrote a plan (GET /plan).")
    has_build: bool = Field(default=False, description="True once the coding agent has a project folder (GET /implementation).")
    reopen_actions: list[Literal["change", "replan"]] = Field(
        default_factory=list, description='A finished, built project still accepts these as {"type": "reopen"} replies.')
    # Pipeline view (9.3): where the graph is, independent of the in-memory progress lines.
    current_node: str | None = Field(default=None, description="Last node that finished (written by the node itself).")
    next_nodes: list[str] = Field(default_factory=list,
                                  description="Nodes LangGraph runs next. While running, the first one is the node in progress.")
    started_at: str | None = None
    active_seconds: float = Field(default=0.0, description="Time spent inside nodes so far (pauses excluded).")
    counters: Counters = Field(default_factory=Counters)
    cancelled: bool = Field(default=False, description="True while a run the user stopped (POST /cancel) waits for "
                            "{\"type\": \"continue\"}: run_state is 'interrupted' but nothing went wrong.")


class ReportResponse(BaseModel):
    thread_id: str
    workflow_status: str
    report: FinalReport


class BriefResponse(BaseModel):
    """The validated problem statement + solution brief (spec §4-5), or the draft the validator is checking right now."""

    thread_id: str
    workflow_status: str | None = None
    brief: ProblemBrief
    markdown: str = Field(description="Rendered brief: sections 1-9 and the references (no appendix).")
    validation: BriefValidation | None = Field(description="The validator's result; null while is_draft.")
    is_draft: bool = Field(default=False, description="True = the validator is still checking this draft (speed: the "
                           "user can read it ~15 s earlier); the checks and open issues arrive with the validated brief.")
    approved_at: str | None = Field(default=None, description="Set once the user approved exactly this brief.")
    review_round: int = Field(default=0, description="Change requests made so far.")


class PlanResponse(BaseModel):
    """The implementation plan (spec §7), readable from the plan review pause on."""

    thread_id: str
    workflow_status: str | None = None
    plan: ImplementationPlan
    markdown: str
    revision: int = 0
    model: str = Field(default="", description="Model that wrote it (after the availability check).")
    approved_at: str | None = Field(default=None, description="Set once the user approved exactly this plan.")
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="The implementer's work list.")


class ImplementationResponse(BaseModel):
    """The coding agent's work (M8/M9): tasks with their verify results, the attempt log, the last build check."""

    thread_id: str
    workflow_status: str | None = None
    workspace_dir: str | None = None
    current_task_id: str | None = None
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="{id, title, phase, status, attempts, result}; "
                                        "status ∈ pending | done | failed | blocked | skipped (done = verify passed).")
    log: list[dict[str, Any]] = Field(default_factory=list, description="One entry per attempt, newest last.")
    cost_usd: float = 0.0
    build: dict[str, Any] | None = Field(default=None, description="Last build check: {round, passed, steps}.")


class UsageResponse(BaseModel):
    """What a session cost (M11, usage.session_cost): the builder's own model calls (measured since M11) + the coding
    agent (Agent SDK cost per attempt), per phase, for the first build and per change request, and step by step."""

    thread_id: str
    total_usd: float
    llm_usd: float
    agent_usd: float
    ask_usd: float | None = Field(default=None, description="Ask-mode replies (usage_events); None = not readable.")
    llm_budget_usd: float
    agent_budget_usd: float
    llm_measured_since: str | None = Field(default=None, description="First metered step; None = the builder's own "
                                           "calls were never measured in this session (it ran before M11).")
    unpriced_models: list[str] = Field(default_factory=list)
    prompt_versions: dict[str, int] = Field(default_factory=dict, description="prompt id -> version used (prompts.py)")
    models_used: list[str] = Field(default_factory=list)
    prices_as_of: str
    phases: list[dict[str, Any]] = Field(default_factory=list, description="{phase, llm_usd, agent_usd, total_usd}")
    first_build: dict[str, Any] = Field(default_factory=dict, description="{llm_usd, agent_usd, total_usd} before the "
                                        "first change request")
    changes: list[dict[str, Any]] = Field(default_factory=list, description="{round, action, request, at, llm_usd, "
                                          "agent_usd, total_usd, tasks}")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="llm steps (one per node run) and agent "
                                        "attempts, oldest first")


class MetricsResponse(BaseModel):
    """The builder's own model usage across sessions (usage_events; Ask included, the coding agent not)."""

    since: str
    days: int
    total: dict[str, Any]
    by_node: list[dict[str, Any]]
    by_day: list[dict[str, Any]]
    calls_by_model: dict[str, int]
    tools: list[dict[str, Any]] = Field(default_factory=list, description="tool_calls per source + tool: {source, tool, "
                                        "calls, failed, refused, timed_out, avg_seconds}")
    agent: dict[str, Any] = Field(default_factory=dict, description="Coding-agent spend of sessions saved in "
                                  "decision_sessions.metrics (completed ones): {sessions, cost_usd}")


class ToolCallView(BaseModel):
    source: Literal["agent", "sandbox", "chat", "search"]
    tool: str
    target: str
    label: str = ""
    ok: bool
    reason: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    duration_seconds: float | None = None
    at: str


class ToolCallList(BaseModel):
    """A session's tool calls, newest first (tool_calls table; empty with PERSIST_RESULTS=false)."""

    thread_id: str
    calls: list[ToolCallView]
    counts: dict[str, int] = Field(default_factory=dict, description="{total, failed, denied_or_refused}")


class PreviewResponse(BaseModel):
    """The session's dev server, read live from the process manager (not from the checkpoint)."""

    thread_id: str
    state: Literal["starting", "ready", "failed", "stopped"]
    url: str | None = None
    port: int | None = None
    command: str
    last_error: str | None = None
    log_tail: str = ""
    started_at: str | None = None
    ready_at: str | None = None
    render: dict | None = Field(default=None, description="Render check of this dev server run in headless Chrome "
                                "(workspace/render_check.py): status ok / warnings / blank / skipped, errors, text_chars.")


class AppSettingVariable(BaseModel):
    name: str
    set: bool = Field(description="A value was saved (the value itself is never returned).")
    help: list[str] = Field(default_factory=list, description="Comment lines above it in the app's .env.example.")
    example: str = ""
    public: bool = Field(description="Bundled into the browser code by the app's framework (VITE_, NEXT_PUBLIC_...).")


class AppSettingGuide(BaseModel):
    service: str
    url: str
    steps: list[str]


class AppDatabase(BaseModel):
    """Supabase apps: the migrations the builder can run, and the last read-only check of the user's project."""

    migrations: list[str] = Field(description="Files of app/supabase/migrations, in the order they run.")
    tables: list[str] = Field(description="Tables those files create (what the check looks for).")
    check: dict | None = Field(default=None, description="status ready / missing / unknown / not_checked, missing "
                               "tables, errors, at. None = not checked with the URL saved now.")
    setup: dict | None = Field(default=None, description="After POST .../database/setup: ok, error, per-file status.")


class AppSettingsResponse(BaseModel):
    """The settings the generated app needs (its .env.example), for the Preview tab's form. Values stay on the
    builder's machine in .builder/app.env and go to the dev server only: never to the code, a model or the download."""

    thread_id: str
    variables: list[AppSettingVariable]
    missing: list[str]
    guides: list[AppSettingGuide]
    preview: PreviewResponse | None = Field(default=None, description="After a save: the restarted preview.")
    database: AppDatabase | None = Field(default=None, description="Only for apps with Supabase migrations.")


class DatabaseSetupRequest(BaseModel):
    db_url: str = Field(min_length=10, max_length=2000, description="The project's Postgres connection string (with "
                        "the password). Used for this run only: never stored, logged or given to a model.")


class AppSettingsUpdate(BaseModel):
    values: dict[str, str] = Field(description="Name → value; an empty value removes a saved one.")


class CodeFile(BaseModel):
    path: str = Field(description="Relative POSIX path inside the project folder.")
    content_b64: str


class CodeExportResponse(BaseModel):
    """The generated project's files for "Download code" (node_modules, build output, .git, .env* left out)."""

    thread_id: str
    folder_name: str = Field(description='Suggested folder name, e.g. "simple-calculator-web-app".')
    total_bytes: int
    skipped: list[str] = Field(default_factory=list, description="What was left out, with the reason.")
    files: list[CodeFile]


class ArtifactView(BaseModel):
    kind: Literal["brief", "plan"]
    version: int
    content_hash: str
    approved_at: str | None = None
    created_at: str
    markdown: str


class ArtifactList(BaseModel):
    thread_id: str
    artifacts: list[ArtifactView]


class EvidenceResponse(BaseModel):
    thread_id: str
    count: int
    verification_counts: dict[str, int] = Field(description="verification_status -> number of evidence items")
    evidence: list[Evidence]


class ErrorResponse(BaseModel):
    """Every error the API returns has this shape: {"error": {"code": ..., "message": ...}}."""

    error: ErrorInfo


# --- live snapshot (GET /live): everything the agents produced so far ----------------------------

class CaseView(BaseModel):
    """What the system understood about the user (intake + clarification)."""

    project_name: str | None = None
    project_category: str | None = None
    idea_summary: str | None = None
    user_context: str = ""
    project_profile: dict[str, str] = Field(default_factory=dict)
    requested_features: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, str] = Field(default_factory=dict)
    missing_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    risk_flags: list[str] = Field(default_factory=list)
    withdrawn_risk_flags: list[dict[str, str]] = Field(default_factory=list, description='{"flag", "reason"}')


class ResearchView(BaseModel):
    passes: int = 0
    queries: list[str] = Field(default_factory=list)
    evidence_by_domain: dict[str, int] = Field(default_factory=dict)
    evidence_gaps: list[str] = Field(default_factory=list)
    conflicting_claims: list[dict[str, Any]] = Field(default_factory=list)
    rejected_count: int = 0
    domain_summaries: dict[str, str] = Field(default_factory=dict)
    research_focus: list[str] = Field(default_factory=list, description="What the next (follow-up) pass must look for.")


class DebateView(BaseModel):
    round: int = 0
    proposals: list[SolutionProposal] = Field(default_factory=list)
    criticisms: list[Criticism] = Field(default_factory=list)
    scores: list[ProposalScore] = Field(default_factory=list)
    verdict: Verdict | None = None
    proposer_status: str = Field(default="", description="ok | thin | declined | no_evidence")
    proposer_notes: str = ""


class VerificationView(BaseModel):
    results: list[ClaimVerification] = Field(default_factory=list)
    verdict: dict[str, Any] | None = None
    unresolved_questions: list[str] = Field(default_factory=list)


class LiveSnapshot(BaseModel):
    """The agents' work so far, straight from the checkpoint. Readable while running, paused or finished."""

    thread_id: str
    run_state: RunState
    workflow_status: str | None = None
    current_node: str | None = None
    case: CaseView
    research: ResearchView
    debate: DebateView
    verification: VerificationView
    metrics: dict[str, Any] | None = Field(default=None, description="Set by completion when the session finished.")


# --- session list (GET /api/decisions) -----------------------------------------------------------

class SessionSummary(BaseModel):
    thread_id: str
    question: str
    mode: str = "full"
    project_name: str | None = None
    status: str
    risk_flag_count: int = 0
    created_at: str
    updated_at: str | None = None
    completed_at: str | None = None


class SessionList(BaseModel):
    sessions: list[SessionSummary]


# --- builder chat (api/chat.py) -------------------------------------------------------------------

class ChatMessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ClarificationTurn(BaseModel):
    question: str
    answer: str


class ReviewTurn(BaseModel):
    """One reply of the user to a brief or plan review (approve, or a change request with its text)."""

    kind: Literal["brief", "plan"]
    round: int
    action: Literal["approve", "request_changes"]
    feedback: str = ""
    target: str | None = Field(default=None, description="Brief only: where the change went (resolved target if known).")
    at: str


class ChangeTurn(BaseModel):
    """One reply at the change-request pause, with the coding-agent task it created (change only)."""

    round: int
    action: Literal["change", "replan", "finish"]
    request: str = ""
    at: str
    task_id: str | None = Field(default=None, description="The C<n> task of a change (None for replan / finish).")
    task_status: str | None = Field(default=None, description="pending | done | failed | blocked | skipped.")
    cost_usd: float | None = Field(default=None, description="What this change cost so far (model calls + coding "
                                   "agent until the next reply at the change pause; usage.session_cost). None for finish.")


class ChatTranscript(BaseModel):
    """Everything the builder chat shows besides the live status: the onboarding (first message, the questions
    already answered, the summary), the user's review replies and change requests (with timestamps, so the page
    can order them) and the Ask-mode messages."""

    thread_id: str
    mode: str
    question: str | None = None
    project_name: str | None = None
    clarifications: list[ClarificationTurn] = Field(default_factory=list, description="Answered onboarding questions, in order.")
    onboarding_summary: dict[str, str] | None = Field(default=None, description="Short summary of the outcome once the report exists: opening, details (markdown), invitation.")
    ready: bool = Field(description="True once the report exists: Ask mode is available.")
    reviews: list[ReviewTurn] = Field(default_factory=list, description="Brief and plan review replies, oldest first.")
    changes: list[ChangeTurn] = Field(default_factory=list, description="Change-request replies, oldest first.")
    messages: list[ChatMessageView] = Field(default_factory=list, description="Ask-mode messages, oldest first.")


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=4000)


class MemoryFact(BaseModel):
    fact: str
    source: str            # "onboarding" | "chat"
    created_at: str


class MemoryList(BaseModel):
    facts: list[MemoryFact]
