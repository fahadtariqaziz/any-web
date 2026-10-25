"""Speed work (2026-10-26): calls that used to wait for each other now run in parallel, the nodes stay the same.

- the claim checks run with the critiques (critic node), the evidence checker only picks the winner's check;
- the report narrative is written by the brief writer, in parallel with the brief parts;
- the research plan is made in parallel with the last clarification call and reused by the research node.
"""

import pytest

from ai_decision_arena.nodes.brief_writer import brief_writer_node
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.evidence_checker import evidence_checker_node
from ai_decision_arena.nodes.final_report import final_report_node
from ai_decision_arena.nodes.research import research_node
from tests.conftest import finish_session


@pytest.fixture
def finished(graph, fake_llm, fake_search) -> dict:
    config = {"configurable": {"thread_id": "speed-fixture"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    state = finish_session(graph, config)
    fake_llm.calls.clear()
    return state


def test_claims_are_checked_with_the_critiques_and_the_checker_makes_no_call(finished, fake_llm):
    assert set(finished["proposal_checks"]) == {p["proposal_id"] for p in finished["proposals"]}
    out = evidence_checker_node(finished)
    assert fake_llm.count("ProposalVerification") == 0
    assert out["verification_results"] and out["checker_verdict"]["claims_checked"] == len(out["verification_results"])


def test_checker_still_checks_when_no_stored_check_exists(finished, fake_llm):
    evidence_checker_node(finished | {"proposal_checks": {}})
    assert fake_llm.count("ProposalVerification") == 1


def test_report_narrative_is_written_by_the_brief_writer_in_parallel(finished, fake_llm):
    assert finished["final_report"]["overview"]                       # the finished session has its narrative
    out = final_report_node(finished)
    assert fake_llm.count("ReportNarrative") == 0 and out["final_report"]["overview"] == ""
    written = brief_writer_node(finished | out)
    assert fake_llm.count("ReportNarrative") == 1 and written["final_report"]["overview"]
    again = brief_writer_node(finished | out | written)                 # narrative present: not written twice
    assert fake_llm.count("ReportNarrative") == 1 and "final_report" not in again


def test_research_plan_is_made_with_the_last_clarification_and_reused(base_state, fake_llm, fake_search):
    state = base_state | {"clarification_round_count": 1, "clarification_answers": {"Which platform?": "web"}}
    out = clarification_node(state)
    assert not out["need_clarification"] and out["research_plan"]["queries"]
    assert fake_llm.count("ResearchPlan") == 1
    researched = research_node(state | out)
    assert fake_llm.count("ResearchPlan") == 1 and researched["research_plan"] is None
    assert researched["research_queries"]
