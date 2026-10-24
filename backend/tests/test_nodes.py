"""Node-level behaviour with the fake LLM: the Python around each call is what we test."""

import pytest

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.intake import InvalidInputError, intake_node
from ai_decision_arena.nodes.judge import judge_node, weighted_total
from ai_decision_arena.nodes.proposer import proposer_node
from tests.conftest import build_intake, build_judgement


def test_intake_rejects_short_input_without_calling_the_llm(fake_llm):
    with pytest.raises(InvalidInputError):
        intake_node({"question": "ab"})
    assert fake_llm.calls == []


def test_intake_rejects_off_topic_input(fake_llm):
    def off_topic(system, user):
        return build_intake(system, user).model_copy(update={"is_app_request": False})
    fake_llm.overrides[S.IntakeResult] = off_topic
    with pytest.raises(InvalidInputError, match="doesn't look like"):
        intake_node({"question": "can i do fun"})


def test_intake_initialises_counters(fake_llm):
    out = intake_node({"question": "A habit tracker app for students", "user_context": ""})
    assert out["status"] == "intake"
    assert out["project_name"] == "a habit tracker app for students"
    assert (out["clarification_round_count"], out["research_retry_count"], out["debate_round"]) == (0, 0, 0)
    assert out["missing_information"] and out["started_at"]


def test_clarification_asks_in_round_one_and_merges_answers_later(fake_llm, base_state):
    first = clarification_node(base_state)
    assert first["need_clarification"] is True
    assert len(first["clarification_questions"]) == 2
    assert first["status"] == "awaiting_clarification"

    answered = dict(base_state, clarification_round_count=1,
                    clarification_answers={q: "2 years" for q in first["clarification_questions"]})
    second = clarification_node(answered)
    assert second["need_clarification"] is False
    assert second["status"] == "researching"
    assert second["project_profile"]["audience"] == "university students"
    assert second["assumptions"]            # never continues silently


def test_three_clarification_rounds_are_allowed_but_not_four(fake_llm, base_state):
    def always_asks(system, user):
        from tests.conftest import build_clarification
        r = build_clarification(system, user)
        return r.model_copy(update={"need_clarification": True, "questions": ["Anything else about the users?"], "assumptions": []})
    fake_llm.overrides[S.ClarificationResult] = always_asks
    assert get_settings().max_clarification_rounds == 3
    assert clarification_node(dict(base_state, clarification_round_count=2))["need_clarification"] is True
    assert clarification_node(dict(base_state, clarification_round_count=3))["need_clarification"] is False


def test_clarification_never_asks_past_the_round_cap(fake_llm, base_state):
    state = dict(base_state, clarification_round_count=get_settings().max_clarification_rounds)
    out = clarification_node(state)
    assert out["need_clarification"] is False
    assert out["clarification_questions"] == []


def test_clarification_drops_questions_already_answered(fake_llm, base_state):
    state = dict(base_state, clarification_answers={"Who are the main users of this app?": "students"})
    out = clarification_node(state)
    assert "Who are the main users of this app?" not in out["clarification_questions"]
    assert out["clarification_questions"] == ["Which features must the first version have?"]


def _evidence(eid: str, domain: str) -> dict:
    return S.Evidence(evidence_id=eid, domain=domain, source_title="t", source_url="https://e.org/x",
                      source_type="research_paper", relevant_excerpt="e", is_direct_quote=False,
                      relevance_score=0.9).model_dump(mode="json")


def test_proposer_builds_plans_per_lane_and_drops_unknown_citations(fake_llm, base_state):
    state = dict(base_state, evidence=[_evidence("ev_001", "apps"), _evidence("ev_002", "papers")])

    def cites_unknown(system, user):
        from tests.conftest import build_proposer
        out = build_proposer(system, user)
        for p in out.plans:
            p.supporting_evidence_ids = p.supporting_evidence_ids + ["ev_999"]
        return out
    fake_llm.overrides[S.ProposerOutput] = cites_unknown

    out = proposer_node(state)
    ids = sorted(p["plan_id"] for p in out["care_plans"])
    assert ids == ["apps_a", "apps_b", "papers_a", "papers_b"]      # no tech evidence → no tech plan
    assert out["proposer_lane_status"] == {"apps": "ok", "papers": "ok", "tech": "no_evidence"}
    for p in out["care_plans"]:
        assert "ev_999" not in p["supporting_evidence_ids"]
        assert any("not found" in g for g in p["evidence_gaps"])
    assert out["debate_round"] == 1 and out["criticisms"] == [] and out["scores"] == []


def _plans(*ids: str) -> list[dict]:
    return [S.CarePlan(name=i, summary="s", daily_routine=[], diet=[], medications_treatments=[], expected_timeline="",
                       prevalence_and_outlook="", benefits=[], drawbacks_risks=[], assumptions=[], difficulty="low",
                       safety_notes="", supporting_evidence_ids=[], evidence_gaps=[], plan_id=i,
                       domain=i.split("_")[0], round=1).model_dump(mode="json") for i in ids]


def test_judge_computes_totals_in_python_and_picks_a_winner_per_lane(fake_llm, base_state):
    state = dict(base_state, debate_round=1, care_plans=_plans("apps_a", "apps_b", "papers_a", "tech_a"),
                 proposer_lane_status={"apps": "ok", "papers": "ok", "tech": "ok"})
    out = judge_node(state)
    assert out["verdict"]["decision"] == "proceed"
    assert out["verdict"]["winning_plan_ids"] == {"apps": "apps_a", "papers": "papers_a", "tech": "tech_a"}
    weights = get_settings().rubric_weights
    for s in out["scores"]:
        assert s["weighted_total"] == weighted_total(S.PlanScore.model_validate(s), weights)
    assert out["status"] == "verifying"


def test_judge_requests_research_when_a_lane_is_insufficient(fake_llm, base_state):
    def insufficient(system, user):
        j = build_judgement(system, user)
        return j.model_copy(update={"evidence_sufficient": False, "insufficiency_reason": "thin",
                                    "required_evidence": ["prevalence data"]})
    fake_llm.overrides[S.DomainJudgement] = insufficient
    state = dict(base_state, debate_round=1, care_plans=_plans("apps_a", "papers_a", "tech_a"),
                 proposer_lane_status={"apps": "ok", "papers": "ok", "tech": "ok"})
    out = judge_node(state)
    assert out["verdict"]["decision"] == "request_more_research"
    assert out["research_retry_count"] == 1
    assert "prevalence data" in out["research_focus"]


def test_judge_stops_looping_at_the_caps(fake_llm, base_state):
    def insufficient(system, user):
        return build_judgement(system, user).model_copy(update={"evidence_sufficient": False, "insufficiency_reason": "thin"})
    fake_llm.overrides[S.DomainJudgement] = insufficient
    s = get_settings()
    state = dict(base_state, debate_round=s.max_debate_rounds, research_retry_count=s.max_research_retries,
                 care_plans=_plans("apps_a", "papers_a", "tech_a"))
    out = judge_node(state)
    assert out["verdict"]["decision"] == "insufficient_evidence"
    assert "research_retry_count" not in out
