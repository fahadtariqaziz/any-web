"""Cross-field validators: these are what make call_structured retry with useful feedback."""

import pytest
from pydantic import ValidationError

from ai_decision_arena import schemas as S
from ai_decision_arena.config import Settings, get_settings


def test_clarification_needs_questions_when_asking():
    with pytest.raises(ValidationError, match="questions is empty"):
        S.ClarificationResult(need_clarification=True, questions=[], reason="", new_profile_facts=[], new_features=[],
                              new_constraints=[], new_risk_flags=[], withdrawn_risk_flags=[], refined_project_name="",
                              refined_idea_summary="", assumptions=[])


def test_research_plan_must_cover_every_domain():
    q = S.SearchQuery(query="x", domain="apps", topic="user_complaints", preferred_domains=[])
    with pytest.raises(ValidationError, match="missing"):
        S.ResearchPlan(search_term="x", queries=[q, q, q])


def _score(pid: str, criteria: list[str]) -> S.ProposalScore:
    return S.ProposalScore(proposal_id=pid, criterion_scores=[S.CriterionScore(criterion=c, score=5, explanation="") for c in criteria],
                           key_benefits=[], key_drawbacks=[], confidence="low", confidence_reason="",
                           supporting_evidence_ids=[], remaining_risks=[])


def _judgement(scores, **kw) -> S.ProposalJudgement:
    base = dict(reasoning="r", scores=scores, comparison="c", evidence_sufficient=True, insufficiency_reason="",
                required_evidence=[], domain_coverage=[], material_contradictions=[], clarification_questions=[])
    return S.ProposalJudgement(**(base | kw))


def test_judgement_scores_must_match_the_rubric():
    criteria = list(get_settings().rubric_weights)
    _judgement([_score("proposal_a", criteria)])
    with pytest.raises(ValidationError, match="exactly these criteria"):
        _judgement([_score("proposal_a", criteria[:-1])])
    with pytest.raises(ValidationError, match="duplicate"):
        _judgement([_score("proposal_a", criteria), _score("proposal_a", criteria)])


def test_judgement_insufficient_needs_a_reason():
    with pytest.raises(ValidationError, match="insufficiency_reason"):
        _judgement([], evidence_sufficient=False)


def test_verification_material_failures_need_gaps():
    claim = S.ClaimCheck(claim="x", evidence_ids=[], status="unsupported", notes="", is_anecdotal=False, is_material=True)
    with pytest.raises(ValidationError, match="material_gaps"):
        S.ProposalVerification(claims=[claim], overall="", material_gaps=[])


def test_proposal_and_evidence_id_patterns():
    with pytest.raises(ValidationError):
        S.Criticism(proposal_id="plan_1", points=[], overall_assessment="")
    S.Criticism(proposal_id="proposal_b", points=[], overall_assessment="")
    with pytest.raises(ValidationError):
        S.Evidence(evidence_id="x", domain="apps", source_title="t", source_url="https://e.org", source_type="other",
                   relevant_excerpt="e", is_direct_quote=False, relevance_score=0.5)
    S.Evidence(evidence_id="ev_001", domain="apps", source_title="t", source_url="https://e.org", source_type="other",
               relevant_excerpt="e", is_direct_quote=False, relevance_score=0.5)


def test_rubric_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="add up to 1.0"):
        Settings(rubric_weights={"requirements_alignment": 0.5, "feasibility": 0.6})
    assert abs(sum(get_settings().rubric_weights.values()) - 1.0) < 0.001
    assert set(get_settings().rubric_weights) == {"requirements_alignment", "problem_relevance", "evidence_quality",
                                                  "feasibility", "completeness"}
