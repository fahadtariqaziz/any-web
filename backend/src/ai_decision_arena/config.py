"""All app settings in one typed place.

Every value has a safe default and can be overridden from backend/.env or a real
environment variable with the same name in UPPER_CASE, e.g. MAX_DEBATE_ROUNDS=3.

Usage:
    from ai_decision_arena.config import get_settings
    settings = get_settings()
    settings.max_debate_rounds

Session modes: a session runs in "full" mode (the admin view: every pause, every loop) or "quick" mode
(the patient chat: a faster model, less research, no loops). The graph wraps every node in
`session_mode(state["mode"])`, and inside it get_settings() returns the quick settings. The worker
threads of a node (ContextThreadPoolExecutor) copy the context, so the three lanes see the same mode.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"   # backend/.env
REPO_ROOT = Path(__file__).resolve().parents[3]           # ai-lab-2/

# Copy .env into os.environ too: LangChain/LangSmith/Tavily read their keys from there.
# Real environment variables win over .env (override=False).
load_dotenv(ENV_FILE, override=False)

# Judge rubric: criterion -> weight. The descriptions are shown to the Judge verbatim.
DEFAULT_RUBRIC = {
    "requirements_alignment": 0.30,
    "problem_relevance": 0.20,
    "evidence_quality": 0.20,
    "feasibility": 0.20,
    "completeness": 0.10,
}
RUBRIC_DESCRIPTIONS = {
    "requirements_alignment": "Matches THIS user's clarified requirements and constraints (audience, must-have features, "
                              "platform, budget, timeline, technology preferences).",
    "problem_relevance": "Addresses the underlying problem and the gaps users of existing alternatives complain about, "
                         "instead of copying an existing app.",
    "evidence_quality": "Backed by relevant, strong evidence (papers, official docs, maintained repositories, aggregated "
                        "reviews > single anecdotes), with few gaps.",
    "feasibility": "Buildable as a first version within the constraints: proven technologies, available APIs, manageable "
                   "dependencies and risks.",
    "completeness": "Covers users, MVP features, user journey, architecture, technologies, security / privacy and future scope.",
}


SessionMode = Literal["full", "quick"]

# Patient chat ("quick" mode): the whole onboarding should take about 30 seconds after the questions.
# Same agents, same order; only less of everything. Applied on top of the normal settings.
QUICK_OVERRIDES = {
    "llm_max_retries": 1,
    "llm_timeout_seconds": 40,
    "max_clarification_rounds": 1,
    "max_research_retries": 0,              # no automatic loops: one research pass, one debate round
    "max_debate_rounds": 1,
    "session_time_budget_seconds": 120,
    "queries_per_domain": 2,           # one general query + the key-topic query per domain
    "max_results_per_query": 3,
    "max_hits_per_domain": 4,          # extraction is the slowest step: fewer sources = less output
    "max_evidence_per_domain": 4,
    "max_excerpt_chars": 600,
    "tavily_search_depth": "basic",         # (the apps domain keeps "advanced": basic review / forum snippets are too short)
    "tavily_timeout_seconds": 6,            # a hanging search is retried once quickly instead of waiting
    "search_max_retries": 1,
    "max_brief_revisions": 0,               # the brief goes out with its open issues listed
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # --- secrets (SecretStr prints as '**********', so keys never leak into logs) ---
    anthropic_api_key: SecretStr
    tavily_api_key: SecretStr
    langsmith_api_key: SecretStr | None = None

    # --- Claude ---
    anthropic_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = Field(default=4000, ge=256, le=32000)
    llm_timeout_seconds: float = Field(default=90, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5, description="Retries for API errors and invalid structured output.")
    planner_model: str = Field(default="claude-opus-5-5", description="Model of the planner (checked against the API's "
                               "model list at startup; falls back to anthropic_model with a warning).")
    planner_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="high", description="Reasoning effort of the planner (Opus 5.5 defaults to medium; planning deserves more).")
    planner_max_tokens: int = Field(default=16000, ge=4000, le=32000)
    planner_timeout_seconds: float = Field(default=600, gt=0, description="A full plan at high effort takes minutes.")
    implementer_model: str = Field(default="claude-sonnet-5-5", description="Model of the coding agent (M8, Claude "
                                   "Agent SDK; checked against the model list like the planner's).")
    implementer_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="medium", description="Sonnet 5.5's recalibrated levels: medium is the recommended start for agentic coding.")
    implementer_max_turns: int = Field(default=40, ge=5, le=200, description="Agent turns per task attempt.")
    implementer_task_timeout_seconds: float = Field(default=900, gt=0, description="Wall clock per task attempt.")
    implementer_task_budget_usd: float = Field(default=2.0, gt=0, description="Agent cost cap per task attempt.")
    implementation_budget_usd: float = Field(default=15.0, gt=0, description="Agent cost cap per session: no new "
                                             "task attempt starts once the session spent this much.")
    max_build_fix_rounds: int = Field(default=2, ge=0, le=5, description="Times a failing build check sends a fix "
                                      "task back to the coding agent before the preview starts anyway (per change).")
    max_change_requests: int = Field(default=10, ge=0, le=50, description="Change requests per session from the "
                                     "preview pause; after that the session can only finish.")
    preview_idle_check_seconds: float = Field(default=300, ge=5, description="How often idle previews are looked for.")
    max_task_attempts: int = Field(default=2, ge=1, le=5, description="Attempts per task (a retry gets the failing "
                                   "verify output); then the task is failed and its dependants blocked.")
    quick_model: str = Field(default="claude-haiku-5-5", description="Model for every agent of a quick (patient chat) session.")
    fallback_model: str = Field(default="claude-haiku-5-5", description="Backup model: a graph agent's call is repeated "
                                "once on it when the main model fails. Empty = no fallback.")
    quick_fallback_model: str = Field(default="claude-sonnet-5-5", description="Backup model of a quick session.")
    chat_model: str = Field(default="claude-sonnet-5-5", description="Model of the builder chat's Ask mode.")
    session_mode: SessionMode = Field(default="full", description="Set by session_mode(); not meant for .env.")
    quick_double_check: bool = Field(default=False, description="Quick sessions also run the Critic and the Evidence "
                                     "Checker (about +20 s). Off by default to keep onboarding near 30 s.")

    # --- loop limits (see handoff.md for what each counter means) ---
    max_clarification_rounds: int = Field(default=3, ge=0, le=5)
    max_research_retries: int = Field(default=2, ge=0, le=5)
    max_debate_rounds: int = Field(default=2, ge=1, le=5)
    max_brief_revisions: int = Field(default=2, ge=0, le=5, description="Rewrites of the brief the validator may ask for.")
    max_plan_revisions: int = Field(default=3, ge=0, le=10, description="Plan rewrites the user may request; after that "
                                    "the plan can only be approved.")
    max_review_rounds: int = Field(default=6, ge=1, le=20, description="Change requests on the brief that may re-run "
                                   "earlier steps; after that only wording changes (or approval) are accepted.")
    brief_word_budget: int = Field(default=900, ge=300, le=3000, description="Words of brief sections 1-9 before the "
                                   "appendix (about one page); overflow items move to the appendix.")

    # --- generated projects (M7: workspace/, handoff.md section 6) ---
    generated_projects_dir: Path = Field(default=REPO_ROOT / "generated_projects", description="One folder per session "
                                         "(<dir>/<thread_id>/app + .builder); git-ignored.")
    command_timeout_seconds: float = Field(default=120, gt=0, description="Per sandbox command (tests, builds, ls...).")
    install_timeout_seconds: float = Field(default=600, gt=0, description="Per package install (npm install, uv sync...).")
    command_output_cap_bytes: int = Field(default=20_000, ge=1000, le=1_000_000, description="Tail kept per stream.")
    share_package_cache: bool = Field(default=True, description="Sessions share one npm/uv/pip download cache under "
                                      "<generated_projects_dir>/.shared (content-addressed and integrity-checked; "
                                      "installs are much faster). False = a cache per session.")
    preview_port_range: str = Field(default="4100-4199", pattern=r"^\d{4,5}-\d{4,5}$")
    preview_health_timeout_seconds: float = Field(default=60, gt=0, description="A dev server must answer HTTP in time.")
    preview_idle_minutes: float = Field(default=30, gt=0, description="A preview nobody looked at for this long is stopped.")

    # --- session budget ---
    session_time_budget_seconds: float = Field(default=900, gt=0, description="Active (non-paused) seconds after which no new loops start.")

    # --- research limits (cost control). Research runs 3 domains: research / doctor / patient ---
    queries_per_domain: int = Field(default=3, ge=1, le=6)
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    max_hits_per_domain: int = Field(default=12, ge=3, le=30, description="Hits sent to the extractor per lane.")
    max_evidence_per_domain: int = Field(default=10, ge=1, le=30)
    max_excerpt_chars: int = Field(default=2000, ge=200, le=2000)   # Evidence.relevant_excerpt max_length
    tavily_search_depth: Literal["basic", "advanced"] = "basic"      # advanced = better snippets, 2x credits
    tavily_apps_search_depth: Literal["basic", "advanced"] = "advanced"     # review / forum snippets are short with basic
    tavily_timeout_seconds: float = Field(default=30, gt=0)
    search_max_retries: int = Field(default=2, ge=0, le=5, description="Retries per query for transient Tavily errors.")

    # --- judge rubric: criterion -> weight; must add up to 1.0 ---
    # Override in .env as JSON: RUBRIC_WEIGHTS={"fit_to_user":0.4,...}
    rubric_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_RUBRIC))

    # --- triggers (triggers.py): scheduled check-ins in quiet patient chats ---
    check_ins_enabled: bool = Field(default=True, description="Run the check-in scheduler inside the API process.")
    check_in_quiet_hours: float = Field(default=24, ge=0, description="A chat this many hours quiet gets one check-in.")
    check_in_interval_seconds: float = Field(default=3600, ge=10, description="How often the scheduler looks.")
    check_in_max_per_run: int = Field(default=5, ge=1, le=50, description="Cost cap: check-ins written per run.")

    # --- tracing ---
    langsmith_tracing: bool = True
    langsmith_project: str = "ai-decision-arena"

    # --- infrastructure (used from Phase 7/8) ---
    database_url: str = "postgresql://postgres:password@localhost:5432/ai_decision_arena"
    persist_results: bool = True   # completion saves session/evidence/report to the app tables (PERSIST_RESULTS=false to skip)
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    @field_validator("rubric_weights")
    @classmethod
    def weights_must_sum_to_one(cls, weights: dict[str, float]) -> dict[str, float]:
        if not weights:
            raise ValueError("rubric_weights must not be empty")
        if any(w < 0 for w in weights.values()):
            raise ValueError("rubric weights must be >= 0")
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"rubric weights must add up to 1.0 (got {total:.3f})")
        return weights


_current_mode: ContextVar[str] = ContextVar("session_mode", default="full")


@lru_cache
def _settings_for(mode: str) -> Settings:
    """Build Settings once per mode and reuse them (lru_cache = remember the first result)."""
    base = Settings()
    if mode != "quick":
        return base
    return base.model_copy(update=QUICK_OVERRIDES | {"anthropic_model": base.quick_model, "fallback_model": base.quick_fallback_model,
                                                     "session_mode": "quick"})


def get_settings() -> Settings:
    """The settings of the session mode that is active right now ("full" outside a session_mode block)."""
    return _settings_for(_current_mode.get())


@contextmanager
def session_mode(mode: str | None):
    """Inside this block get_settings() returns the settings for `mode` (None / unknown = "full")."""
    token = _current_mode.set("quick" if mode == "quick" else "full")
    try:
        yield
    finally:
        _current_mode.reset(token)
