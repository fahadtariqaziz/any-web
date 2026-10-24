"""Cross-field validators: these are what make call_structured retry with useful feedback."""

import pytest
from pydantic import ValidationError

from ai_decision_arena import schemas as S
from ai_decision_arena.config import Settings, get_settings


def test_clarification_needs_questions_when_asking():
    with pytest.raises(ValidationError, match="questions is empty"):
        S.ClarificationResult(need_clarification=True, questions=[], reason="", new_profile_facts=[], new_symptoms=[],
                              new_constraints=[], new_red_flags=[], withdrawn_red_flags=[], refined_condition_name="",
                              refined_case_summary="", assumptions=[])


def test_research_plan_must_cover_every_perspective():
    q = S.SearchQuery(query="x", perspective="doctor", topic="diet", preferred_domains=[])
    with pytest.raises(ValidationError, match="missing"):
        S.ResearchPlan(search_term="x", queries=[q, q, q])


def test_judgement_scores_must_match_the_rubric():
    criteria = list(get_settings().rubric_weights)
    good = S.PlanScore(plan_id="doctor_a", criterion_scores=[S.CriterionScore(criterion=c, score=5, explanation="") for c in criteria],
                       key_benefits=[], key_drawbacks=[], confidence="low", confidence_reason="", supporting_evidence_ids=[],
                       remaining_risks=[])
    S.PerspectiveJudgement(reasoning="r", scores=[good], comparison="c", evidence_sufficient=True, insufficiency_reason="",
                           required_evidence=[], clarification_questions=[])
    bad = good.model_copy(update={"criterion_scores": good.criterion_scores[:-1]})
    with pytest.raises(ValidationError, match="exactly these criteria"):
        S.PerspectiveJudgement(reasoning="r", scores=[bad], comparison="c", evidence_sufficient=True, insufficiency_reason="",
                               required_evidence=[], clarification_questions=[])


def test_judgement_insufficient_needs_a_reason():
    with pytest.raises(ValidationError, match="insufficiency_reason"):
        S.PerspectiveJudgement(reasoning="r", scores=[], comparison="c", evidence_sufficient=False, insufficiency_reason="",
                               required_evidence=[], clarification_questions=[])


def test_verification_material_failures_need_gaps():
    claim = S.ClaimCheck(claim="x", evidence_ids=[], status="unsupported", notes="", is_anecdotal=False, is_material=True)
    with pytest.raises(ValidationError, match="material_gaps"):
        S.PlanVerification(claims=[claim], overall="", material_gaps=[])


def test_plan_and_evidence_id_patterns():
    with pytest.raises(ValidationError):
        S.Criticism(plan_id="plan_1", points=[], overall_assessment="")
    with pytest.raises(ValidationError):
        S.Evidence(evidence_id="x", perspective="doctor", source_title="t", source_url="https://e.org", source_type="other",
                   relevant_excerpt="e", is_direct_quote=False, relevance_score=0.5)
    S.Evidence(evidence_id="ev_001", perspective="doctor", source_title="t", source_url="https://e.org", source_type="other",
               relevant_excerpt="e", is_direct_quote=False, relevance_score=0.5)


def test_rubric_weights_must_sum_to_one():
    with pytest.raises(ValidationError, match="add up to 1.0"):
        Settings(rubric_weights={"fit_to_user": 0.5, "safety": 0.6})
    assert abs(sum(get_settings().rubric_weights.values()) - 1.0) < 0.001
