"""Session-level limits shared by the nodes that decide whether to loop."""

from ai_decision_arena.config import get_settings
from ai_decision_arena.state import ArenaState
from ai_decision_arena.usage import llm_cost


def active_seconds(state: ArenaState) -> float:
    return float(state.get("active_seconds", 0.0) or 0.0)


def time_budget_left(state: ArenaState) -> bool:
    """False once the session has spent its active-time budget: no new research/debate loops."""
    return active_seconds(state) < get_settings().session_time_budget_seconds


def loops_allowed(state: ArenaState) -> tuple[bool, bool, bool, list[str]]:
    """(can_debate, can_research, can_clarify, reasons_blocked). A research pass always starts a new debate
    round, so can_research also needs can_debate. The time budget and the LLM cost budget block every automatic
    loop; risk flags are informational and never change routing."""
    settings = get_settings()
    blocked: list[str] = []
    if not time_budget_left(state):
        blocked.append(f"session time budget ({settings.session_time_budget_seconds:.0f}s) spent")
    if llm_cost(state) >= settings.session_llm_budget_usd:
        blocked.append(f"session LLM budget (${settings.session_llm_budget_usd:.2f}) spent")
    can_debate = state.get("debate_round", 0) < settings.max_debate_rounds and not blocked
    can_research = can_debate and state.get("research_retry_count", 0) < settings.max_research_retries
    can_clarify = can_research and state.get("clarification_round_count", 0) < settings.max_clarification_rounds
    if state.get("debate_round", 0) >= settings.max_debate_rounds:
        blocked.append(f"debate rounds ({settings.max_debate_rounds})")
    if state.get("research_retry_count", 0) >= settings.max_research_retries:
        blocked.append(f"research retries ({settings.max_research_retries})")
    return can_debate, can_research, can_clarify, blocked
