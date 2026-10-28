"""Node-level behaviour with the fake LLM: the Python around each call is what we test."""

import pytest

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.clarification import clarification_node
from ai_decision_arena.nodes.critic import critic_node
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
    # 2026-10-29: every question carries answer options (cleaned by Python: no 'Other', no duplicates, at most 4)
    assert first["clarification_options"]["Who are the main users of this app?"] == ["Students", "Small business owners", "My own team"]
    assert first["clarification_options"]["Which features must the first version have?"] == ["Just the basics", "Basics plus sync"]

    answered = dict(base_state, clarification_round_count=1,
                    clarification_answers={q: "2 years" for q in first["clarification_questions"]})
    second = clarification_node(answered)
    assert second["need_clarification"] is False
    assert second["status"] == "researching"
    assert second["project_profile"]["audience"] == "university students"
    assert second["assumptions"]            # never continues silently


def test_one_clarification_round_only_and_at_most_five_questions(fake_llm, base_state):
    """2026-10-29 (user decision): one round, five questions max, whatever the model asks for."""
    def always_asks(system, user):
        r = build_clarification(system, user)
        many = [S.ClarificationQuestion(text=f"Question {i}?", options=[f"a{i}", f"b{i}"]) for i in range(8)]
        return r.model_copy(update={"need_clarification": True, "questions": many, "assumptions": []})
    fake_llm.overrides[S.ClarificationResult] = always_asks
    assert get_settings().max_clarification_rounds == 1
    first = clarification_node(dict(base_state, clarification_round_count=0))
    assert first["need_clarification"] is True and len(first["clarification_questions"]) == 5
    assert set(first["clarification_options"]) == set(first["clarification_questions"])
    assert clarification_node(dict(base_state, clarification_round_count=1))["need_clarification"] is False


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


# --- proposer / critic / judge (+ the winner's claim check) --------------------------------------------------------------

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
    assert out["status"] == "reporting"       # the claim check is folded in: next is the report


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


def test_judge_consolidates_the_winners_claim_check(fake_llm, base_state):
    """Review 2026-10-29: the Evidence Checker node was folded into the Judge. Without a stored check (a state from
    before the critic's pool) the judge makes the one claim-check call itself, for the winner only."""
    state = dict(base_state, evidence=[_evidence("ev_001", "apps")], proposals=_proposals("proposal_a", "proposal_b"))
    out = judge_node(state)
    assert fake_llm.count("ProposalJudgement") == 1 and fake_llm.count("ProposalVerification") == 1
    winner = out["verdict"]["winning_proposal_id"]
    assert winner == "proposal_a" and all(r["proposal_id"] == winner for r in out["verification_results"])
    assert out["checker_verdict"]["decision"] == "proceed" and out["checker_verdict"]["claims_checked"] == 1
    assert out["evidence"][0]["verification_status"] == "verified"
    assert out["status"] == "reporting"                      # next step: the report, no separate checker node


def test_judge_reuses_the_stored_check_and_lists_gaps_as_open_questions(fake_llm, base_state):
    """Fast path (AUTO_LOOPS=false): a material gap of the winner cannot start a research pass, so it becomes an
    'Unverified:' open question in the brief, never hidden."""
    stored = S.ProposalVerification(
        claims=[S.ClaimCheck(claim="AI removes all errors.", evidence_ids=["ev_001"], status="unsupported", notes="capability only",
                             is_anecdotal=False, is_material=True)],
        overall="Thin.", material_gaps=["error rates of automated categorisation"]).model_dump(mode="json")
    state = dict(base_state, evidence=[_evidence("ev_001", "apps")], proposals=_proposals("proposal_a", "proposal_b"),
                 proposal_checks={"proposal_a": stored, "proposal_b": stored})
    out = judge_node(state)
    assert fake_llm.count("ProposalVerification") == 0           # the critic's pool already made the check
    assert out["verdict"]["decision"] == "proceed" and out["checker_verdict"]["decision"] == "proceed"
    assert out["checker_verdict"]["material_gaps"] == ["error rates of automated categorisation"]
    assert out["unresolved_questions"] == ["Unverified: error rates of automated categorisation"]
    assert out["evidence"][0]["verification_status"] == "unsupported"


@pytest.mark.usefixtures("auto_loops")
def test_judge_sends_a_material_gap_of_the_winner_back_to_research_when_loops_are_on(fake_llm, base_state):
    stored = S.ProposalVerification(
        claims=[S.ClaimCheck(claim="AI removes all errors.", evidence_ids=["ev_001"], status="unsupported", notes="capability only",
                             is_anecdotal=False, is_material=True)],
        overall="Thin.", material_gaps=["error rates of automated categorisation"]).model_dump(mode="json")
    state = dict(base_state, evidence=[_evidence("ev_001", "apps")], proposals=_proposals("proposal_a", "proposal_b"),
                 proposal_checks={"proposal_a": stored, "proposal_b": stored})
    out = judge_node(state)
    assert out["verdict"]["decision"] == "request_more_research" and out["checker_verdict"]["decision"] == "request_more_research"
    assert out["research_focus"] == ["error rates of automated categorisation"] and out["research_retry_count"] == 1
    assert "unresolved_questions" not in out                      # researched instead of listed


def test_judge_without_proposals_writes_an_empty_check_without_calling_the_llm(fake_llm, base_state):
    out = judge_node(dict(base_state, proposals=[], proposer_status="declined"))
    assert out["verdict"]["decision"] == "insufficient_evidence" and out["verification_results"] == []
    assert out["checker_verdict"]["claims_checked"] == 0 and out["status"] == "reporting"
    assert fake_llm.calls == []
