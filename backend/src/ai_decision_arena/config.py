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

# Copy .env into os.environ too: LangChain/LangSmith/Tavily read their keys from there.
# Real environment variables win over .env (override=False).
load_dotenv(ENV_FILE, override=False)

# Judge rubric: criterion -> weight. The descriptions are shown to the Judge verbatim.
DEFAULT_RUBRIC = {
    "fit_to_user": 0.30,
    "safety": 0.25,
    "evidence_quality": 0.20,
    "practicality": 0.15,
    "completeness": 0.10,
}
RUBRIC_DESCRIPTIONS = {
    "fit_to_user": "Matches THIS user's condition, profile, symptoms, goals and constraints (diet, budget, preferences).",
    "safety": "Avoids harm: respects contraindications, interactions, red flags; never suggests stopping prescribed treatment.",
    "evidence_quality": "Backed by relevant, strong, recent evidence (guidelines/trials > references > anecdotes), with few gaps.",
    "practicality": "Realistic to follow day to day given the user's situation (effort, cost, access).",
    "completeness": "Covers routine, diet, medications/treatments, expected timeline and prevalence/outlook.",
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
    "queries_per_perspective": 2,           # one topic query + the outlook query per lane
    "max_results_per_query": 3,
    "max_hits_per_perspective": 4,          # extraction is the slowest step: fewer sources = less output
    "max_evidence_per_perspective": 4,
    "patient_lane_extra": 2,                # patient lane: 6 hits / 6 evidence, real stories for the chat's examples
    "min_patient_stories": 2,               # fewer after research → one more patient search (only then, ~10 s)
    "max_excerpt_chars": 600,
    "tavily_search_depth": "basic",         # (the patient lane keeps "advanced": basic forum snippets were too
                                            # short and the patient lane ended up with no plan, tested 2026-10-22)
    "tavily_timeout_seconds": 6,            # a hanging search is retried once quickly instead of waiting
    "search_max_retries": 1,
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
    quick_model: str = Field(default="claude-haiku-5-5", description="Model for every agent of a quick (patient chat) session.")
    fallback_model: str = Field(default="claude-haiku-5-5", description="Backup model: a graph agent's call is repeated "
                                "once on it when the main model fails. Empty = no fallback.")
    quick_fallback_model: str = Field(default="claude-sonnet-5-5", description="Backup model of a quick session.")
    chat_model: str = Field(default="claude-sonnet-5-5", description="Model that answers the patient in the chat.")
    session_mode: SessionMode = Field(default="full", description="Set by session_mode(); not meant for .env.")
    quick_double_check: bool = Field(default=False, description="Quick sessions also run the Critic and the Evidence "
                                     "Checker (about +20 s). Off by default to keep onboarding near 30 s.")

    # --- loop limits (see handoff.md for what each counter means) ---
    max_clarification_rounds: int = Field(default=2, ge=0, le=5)
    max_research_retries: int = Field(default=2, ge=0, le=5)
    max_debate_rounds: int = Field(default=2, ge=1, le=5)

    # --- session budget ---
    session_time_budget_seconds: float = Field(default=900, gt=0, description="Active (non-paused) seconds after which no new loops start.")

    # --- research limits (cost control). Research runs 3 lanes: research / doctor / patient ---
    queries_per_perspective: int = Field(default=3, ge=1, le=6)
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    max_hits_per_perspective: int = Field(default=12, ge=3, le=30, description="Hits sent to the extractor per lane.")
    max_evidence_per_perspective: int = Field(default=10, ge=1, le=30)
    patient_lane_extra: int = Field(default=0, ge=0, le=10, description="Extra hits AND evidence for the patient lane "
                                                                        "(patient stories feed the chat's examples).")
    min_patient_stories: int = Field(default=0, ge=0, le=5, description="Quick mode: fewer patient stories than this "
                                                                        "after research → one extra patient search.")
    max_excerpt_chars: int = Field(default=2000, ge=200, le=2000)   # Evidence.relevant_excerpt max_length
    tavily_search_depth: Literal["basic", "advanced"] = "basic"      # advanced = better snippets, 2x credits
    tavily_patient_search_depth: Literal["basic", "advanced"] = "advanced"   # forum snippets are short with basic
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
