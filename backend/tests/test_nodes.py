"""Node-level behaviour with the fake LLM: the Python around each call is what we test."""

import pytest

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.evidence_checker import evidence_checker_node
from ai_decision_arena.nodes.intake import InvalidInputError, intake_node
from ai_decision_arena.nodes.judge import judge_node, weighted_total
from ai_decision_arena.nodes.proposer import proposer_node
from tests.conftest import _solution, build_clarification, build_intake, build_judgement, build_proposer


# --- intake + clarification -------------------------------------------------------------------------

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


# --- proposer / critic / judge / checker --------------------------------------------------------------

def _evidence(eid: str, domain: str) -> dict:
    return S.Evidence(evidence_id=eid, domain=domain, source_title="t", source_url="https://e.org/x",
                      source_type="review_site", relevant_excerpt="e", is_direct_quote=False,
                      relevance_score=0.9).model_dump(mode="json")


def _proposals(*ids: str) -> list[dict]:
    return [S.SolutionProposal(**_solution(i, ["ev_001"]).model_dump(), proposal_id=i, round=1).model_dump(mode="json") for i in ids]


def test_proposer_assigns_ids_and_drops_unknown_citations(fake_llm, base_state):
    state = dict(base_state, evidence=[_evidence("ev_001", "apps"), _evidence("ev_002", "papers")])

    def cites_unknown(system, user):
        out = build_proposer(system, user)
        for p in out.proposals:
            p.supporting_evidence_ids = p.supporting_evidence_ids + ["ev_999"]
        return out
    fake_llm.overrides[S.ProposerOutput] = cites_unknown

    out = proposer_node(state)
    assert [p["proposal_id"] for p in out["proposals"]] == ["proposal_a", "proposal_b"]
    assert out["proposer_status"] == "ok" and out["proposer_notes"] == ""
    for p in out["proposals"]:
        assert "ev_999" not in p["supporting_evidence_ids"] and "ev_001" in p["supporting_evidence_ids"]
        assert any("not found" in g for g in p["evidence_gaps"])
    assert out["debate_round"] == 1 and out["criticisms"] == [] and out["scores"] == []


def test_proposer_without_evidence_proposes_nothing_and_calls_no_llm(fake_llm, base_state):
    out = proposer_node(base_state)
    assert out["proposals"] == [] and out["proposer_status"] == "no_evidence"
    assert fake_llm.calls == []


def test_proposer_thin_evidence_is_flagged(fake_llm, base_state):
    fake_llm.overrides[S.ProposerOutput] = lambda s, u: S.ProposerOutput(proposals=[], why_fewer_than_two="too thin", evidence_too_thin=True)
    out = proposer_node(dict(base_state, evidence=[_evidence("ev_001", "apps")]))
    assert out["proposals"] == [] and out["proposer_status"] == "thin" and out["proposer_notes"] == "too thin"


def test_critic_reviews_every_proposal_and_owns_the_ids(fake_llm, base_state):
    state = dict(base_state, evidence=[_evidence("ev_001", "apps")], proposals=_proposals("proposal_a", "proposal_b"))

    def wrong_id_and_fake_evidence(system, user):
        from tests.conftest import build_critic
        c = build_critic(system, user)
        c.proposal_id = "proposal_c"                       # the LLM echoed a wrong id
        c.points[0].evidence_ids = ["ev_999"]              # and cited a non-existent record
        c.points[0].basis = "evidence"
        return c
    fake_llm.overrides[S.Criticism] = wrong_id_and_fake_evidence

    out = critic_node(state)
    assert [c["proposal_id"] for c in out["criticisms"]] == ["proposal_a", "proposal_b"]   # Python owns the identity
    assert out["criticisms"][0]["points"][0]["evidence_ids"] == []
    assert out["criticisms"][0]["points"][0]["basis"] == "engineering_judgement"


def test_judge_computes_totals_in_python_and_picks_the_winner(fake_llm, base_state):
    state = dict(base_state, debate_round=1, evidence=[_evidence("ev_001", "apps")],
                 proposals=_proposals("proposal_a", "proposal_b", "proposal_c"), proposer_status="ok")
    out = judge_node(state)
    assert out["verdict"]["decision"] == "proceed"
    assert out["verdict"]["winning_proposal_id"] == "proposal_a"
    assert set(out["verdict"]["domain_status"]) == set(S.DOMAINS)
    weights = get_settings().rubric_weights
    assert len(out["scores"]) == 3
    for s in out["scores"]:
        assert s["weighted_total"] == weighted_total(S.ProposalScore.model_validate(s), weights)
    assert out["status"] == "verifying"


@pytest.mark.usefixtures("auto_loops")
def test_judge_requests_research_when_evidence_is_insufficient(fake_llm, base_state):
    def insufficient(system, user):
        j = build_judgement(system, user)
        return j.model_copy(update={"evidence_sufficient": False, "insufficiency_reason": "thin",
                                    "required_evidence": ["pricing data"]})
    fake_llm.overrides[S.ProposalJudgement] = insufficient
    state = dict(base_state, debate_round=1, proposals=_proposals("proposal_a", "proposal_b"))
    out = judge_node(state)
    assert out["verdict"]["decision"] == "request_more_research"
    assert out["research_retry_count"] == 1
    assert "pricing data" in out["research_focus"]


@pytest.mark.usefixtures("auto_loops")
def test_judge_asks_the_user_when_a_contradiction_needs_resolving(fake_llm, base_state):
    def contradiction(system, user):
        return build_judgement(system, user).model_copy(update={"material_contradictions": ["Offline use vs. cloud sync requirement."]})
    fake_llm.overrides[S.ProposalJudgement] = contradiction
    out = judge_node(dict(base_state, debate_round=1, proposals=_proposals("proposal_a", "proposal_b")))
    assert out["verdict"]["decision"] == "request_clarification"
    assert out["verdict"]["clarification_questions"] and "Offline use" in out["verdict"]["clarification_questions"][0]
    assert out["verdict"]["material_contradictions"] == ["Offline use vs. cloud sync requirement."]


def test_judge_stops_looping_at_the_caps(fake_llm, base_state):
    def insufficient(system, user):
        return build_judgement(system, user).model_copy(update={"evidence_sufficient": False, "insufficiency_reason": "thin"})
    fake_llm.overrides[S.ProposalJudgement] = insufficient
    s = get_settings()
    state = dict(base_state, debate_round=s.max_debate_rounds, research_retry_count=s.max_research_retries,
                 proposals=_proposals("proposal_a", "proposal_b"))
    out = judge_node(state)
    assert out["verdict"]["decision"] == "insufficient_evidence"
    assert "research_retry_count" not in out


@pytest.mark.usefixtures("auto_loops")
def test_judge_with_no_proposals_requests_research_without_calling_the_llm(fake_llm, base_state):
    out = judge_node(dict(base_state, proposals=[], proposer_status="thin", proposer_notes="too thin"))
    assert out["verdict"]["decision"] == "request_more_research"
    assert out["verdict"]["winning_proposal_id"] is None and out["scores"] == []
    assert fake_llm.calls == []


def test_evidence_checker_verifies_only_the_winner(fake_llm, base_state):
    state = dict(base_state, evidence=[_evidence("ev_001", "apps")], proposals=_proposals("proposal_a", "proposal_b"),
                 verdict={"decision": "proceed", "winning_proposal_id": "proposal_b"})
    out = evidence_checker_node(state)
    assert fake_llm.count("ProposalVerification") == 1
    assert all(r["proposal_id"] == "proposal_b" for r in out["verification_results"])
    assert out["checker_verdict"]["decision"] == "proceed" and out["checker_verdict"]["claims_checked"] == 1
    assert out["evidence"][0]["verification_status"] == "verified"


def test_evidence_checker_without_winner_skips_the_llm(fake_llm, base_state):
    out = evidence_checker_node(dict(base_state, proposals=[], verdict={"decision": "insufficient_evidence", "winning_proposal_id": None}))
    assert out["verification_results"] == [] and out["status"] == "reporting"
    assert fake_llm.calls == []
