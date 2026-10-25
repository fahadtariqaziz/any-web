"""limits.loops_allowed: Python, not the LLM, decides whether a loop may start."""

import pytest

from ai_decision_arena.config import get_settings
from ai_decision_arena.limits import loops_allowed, time_budget_left


pytestmark = pytest.mark.usefixtures("auto_loops")     # these tests are about the thorough mode's caps


def test_fresh_session_allows_every_loop():
    can_debate, can_research, can_clarify, blocked = loops_allowed({})
    assert (can_debate, can_research, can_clarify) == (True, True, True)
    assert blocked == []


def test_risk_flags_are_informational_and_block_nothing():
    can_debate, can_research, can_clarify, blocked = loops_allowed({"risk_flags": ["handles card payments"]})
    assert (can_debate, can_research, can_clarify) == (True, True, True)
    assert blocked == []


def test_debate_cap_blocks_debate_and_everything_after():
    s = get_settings()
    state = {"debate_round": s.max_debate_rounds}
    can_debate, can_research, can_clarify, blocked = loops_allowed(state)
    assert (can_debate, can_research, can_clarify) == (False, False, False)
    assert any("debate rounds" in b for b in blocked)


def test_research_cap_blocks_research_but_not_debate():
    s = get_settings()
    state = {"research_retry_count": s.max_research_retries}
    can_debate, can_research, can_clarify, blocked = loops_allowed(state)
    assert can_debate is True
    assert (can_research, can_clarify) == (False, False)
    assert any("research retries" in b for b in blocked)


def test_clarification_cap_blocks_only_clarification():
    s = get_settings()
    state = {"clarification_round_count": s.max_clarification_rounds}
    can_debate, can_research, can_clarify, _ = loops_allowed(state)
    assert (can_debate, can_research, can_clarify) == (True, True, False)


def test_time_budget():
    s = get_settings()
    assert time_budget_left({"active_seconds": 0}) is True
    assert time_budget_left({"active_seconds": s.session_time_budget_seconds + 1}) is False
    _, _, _, blocked = loops_allowed({"active_seconds": s.session_time_budget_seconds + 1})
    assert any("time budget" in b for b in blocked)


def test_fast_path_blocks_every_automatic_loop(monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_loops", False)
    can_debate, can_research, can_clarify, blocked = loops_allowed({})
    assert (can_debate, can_research, can_clarify) == (False, False, False)
    assert any("fast path" in b for b in blocked)
