"""M4: the problem brief (writer + validator) with Claude faked: references from ids only, label fixes,
deterministic checks, rendering, the revision cap and the clarify route."""

import pytest
from langgraph.types import Command
from pydantic import ValidationError

from ai_decision_arena import schemas as S
from ai_decision_arena.brief import (
    SECTION_TITLES,
    assemble_references,
    count_words,
    deterministic_checks,
    normalize,
    render_brief_markdown,
)
from ai_decision_arena.nodes.brief_validator import brief_validator_node
from ai_decision_arena.nodes.brief_writer import brief_writer_node
from tests.conftest import build_brief, build_brief_review, build_clarification, tag

EVIDENCE = [
    {"evidence_id": "ev_001", "source_title": "App reviews", "source_url": "https://example.org/apps/1", "domain": "apps",
     "source_type": "review_site", "verification_status": "verified"},
    {"evidence_id": "ev_002", "source_title": "Library docs", "source_url": "https://example.org/tech/2", "domain": "tech",
     "source_type": "technical_docs", "verification_status": "pending"},
]


def make_brief(content: S.BriefContent | None = None, evidence=EVIDENCE) -> S.ProblemBrief:
    content = content or build_brief("", '<item id="ev_001"')
    return S.ProblemBrief(**content.model_dump(), project_name="habit tracker", revision=0,
                          references=assemble_references(content, evidence))


def check(checks, check_id) -> S.ValidationCheck:
    return next(c for c in checks if c.check_id == check_id)


# --- references, labels, rendering -------------------------------------------------------------------------

def test_references_come_only_from_cited_known_ids():
    content = build_brief("", '<item id="ev_002"')
    content.research_findings.apps_and_feedback.append(S.BriefItem(text="x", label="research_backed", evidence_ids=["ev_001", "ev_999"]))
    refs = assemble_references(content, EVIDENCE)
    assert [r.evidence_id for r in refs] == ["ev_002", "ev_001"]           # numbered by first citation, ev_999 dropped
    assert [r.number for r in refs] == [1, 2]
    assert str(refs[0].url) == "https://example.org/tech/2" and refs[0].title == "Library docs"
    assert "problem_statement" in refs[0].cited_in


def test_normalize_downgrades_unverified_and_unrequired_technology():
    content = build_brief("", '<item id="ev_002"')
    content.problem_statement.statement.label = "verified"                    # ev_002 is only pending
    content.problem_statement.gap = S.BriefItem(text="gap", label="verified", evidence_ids=["ev_001"])   # really verified
    content.architecture.technologies[0].required_by_user = True              # label recommendation
    notes = normalize(content, EVIDENCE)
    assert content.problem_statement.statement.label == "research_backed"
    assert content.problem_statement.gap.label == "verified"
    assert content.architecture.technologies[0].required_by_user is False
    assert len(notes) == 2


def test_render_has_all_ten_sections_and_moves_overflow_to_the_appendix():
    content = build_brief("", '<item id="ev_001"')
    content.requirements.functional = [S.BriefItem(text=f"Requirement {i}.", label="recommendation", evidence_ids=[]) for i in range(7)]
    brief = make_brief(content)
    markdown, words = render_brief_markdown(brief, [{"name": "Rich PWA", "summary": "More features.", "weighted_total": 5.6}],
                                            open_issues=["claims_have_sources: one claim uncited"])
    for title in SECTION_TITLES.values():
        assert f"## {title}" in markdown
    main, appendix = markdown.split("## Appendix")
    assert "Requirement 3." in main and "Requirement 4." not in main and "Requirement 6." in appendix
    assert "Rich PWA" in appendix and "score 5.6/10" in appendix and "one claim uncited" in appendix
    assert "[[1]](https://example.org/apps/1)" in main
    assert 0 < words < 900


def test_renderer_fits_the_page_by_moving_items_to_the_appendix():
    content = build_brief("", '<item id="ev_001"')
    long = "This is a deliberately long statement written to fill the page with many words for the test."
    content.constraints_and_risks.assumptions = [f"{long} ({i})" for i in range(3)]
    content.research_findings.apps_and_feedback = [S.BriefItem(text=f"{long} [{i}]", label="assumption", evidence_ids=[]) for i in range(3)]
    content.proposed_solution.mvp_features = [f"feature {i}" for i in range(6)]
    brief = make_brief(content)
    _, full = render_brief_markdown(brief)
    markdown, fitted = render_brief_markdown(brief, word_budget=full - 40)
    assert fitted <= full - 40
    main, appendix = markdown.split("## Appendix")
    assert "feature 5" in main                                   # floors: the MVP never leaves the main part
    assert "(2)" in appendix or "[2]" in appendix
    assert "label=" not in appendix and "_(assumption)_" in appendix          # overflow items are rendered, not repr'd


def test_word_count_ignores_labels_citations_and_urls():
    assert count_words("Users want offline mode _(research [[1]](https://example.org/a) [[2]](https://x.org/b_c))_") == 4
    assert count_words("Simple app _(you said)_") == 2


# --- deterministic checks ----------------------------------------------------------------------------------

def test_deterministic_checks_pass_on_a_clean_brief():
    brief = make_brief()
    _, words = render_brief_markdown(brief)
    checks = deterministic_checks(brief, EVIDENCE, words, 900)
    assert all(c.passed for c in checks), [c.issue for c in checks if not c.passed]


def test_unknown_ids_uncited_labels_and_foreign_urls_fail():
    content = build_brief("", '<item id="ev_001"')
    content.research_findings.apps_and_feedback.append(S.BriefItem(text="x", label="research_backed", evidence_ids=["ev_999"]))
    content.problem_statement.gap = S.BriefItem(text="See https://made-up.example.com/stats", label="research_backed", evidence_ids=[])
    brief = make_brief(content)
    checks = deterministic_checks(brief, EVIDENCE, 100, 900)
    assert not check(checks, "det_known_evidence_ids").passed and "ev_999" in check(checks, "det_known_evidence_ids").issue
    assert not check(checks, "det_cited_labels_have_evidence").passed
    assert not check(checks, "det_no_unknown_urls").passed and "made-up.example.com" in check(checks, "det_no_unknown_urls").issue


def test_numeric_targets_need_a_basis():
    bad = {"metric": "m", "target": "95%", "basis": "none", "evaluation_method": "e", "evidence_ids": []}
    with pytest.raises(ValidationError, match="basis 'none'"):      # the schema rejects it: the writer retries
        S.BriefPartThree.model_validate(build_brief("", "").model_dump(include=set(S.BriefPartThree.model_fields))
                                        | {"success_criteria": [bad]})
    content = build_brief("", '<item id="ev_001"')
    content.success_criteria = [S.SuccessCriterion(metric="m", target="95%", basis="evidence", evaluation_method="e", evidence_ids=[])]
    checks = deterministic_checks(make_brief(content), EVIDENCE, 100, 900)
    assert not check(checks, "det_targets_have_basis").passed


def test_missing_sections_and_word_budget_fail():
    content = build_brief("", '<item id="ev_001"')
    content.scope.out_of_scope = []
    content.constraints_and_risks.risks = []
    checks = deterministic_checks(make_brief(content), EVIDENCE, 1200, 900)
    sections = check(checks, "det_sections_present")
    assert not sections.passed and "7. scope" in sections.issue and "9. risks" in sections.issue
    budget = check(checks, "det_word_budget")
    assert not budget.passed and budget.severity == "medium" and "1200" in budget.issue


def test_a_brief_without_citations_has_no_references_and_fails():
    brief = make_brief(build_brief("", ""))                 # no evidence ids in the prompt: everything is an assumption
    assert brief.references == []
    assert not check(deterministic_checks(brief, EVIDENCE, 100, 900), "det_sections_present").passed


# --- nodes ---------------------------------------------------------------------------------------------------

@pytest.fixture
def debated(graph, fake_llm, fake_search) -> dict:
    """The state of a finished fake session (debate, report and an approved brief)."""
    config = {"configurable": {"thread_id": "brief-fixture"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    questions = graph.get_state(config).interrupts[0].value["questions"]
    graph.invoke(Command(resume={"answers": {q: "x" for q in questions}}), config)
    state = dict(graph.get_state(config).values)
    fake_llm.calls.clear()
    return state


def test_writer_builds_brief_with_python_references(debated, fake_llm):
    out = brief_writer_node(debated)
    brief = S.ProblemBrief.model_validate(out["brief"])
    known = {e["evidence_id"]: e for e in debated["evidence"]}
    assert brief.references and all(str(r.url) == known[r.evidence_id]["source_url"] for r in brief.references)
    assert brief.revision == 0 and out["status"] == "validating_brief"
    assert "## 10. References" in out["brief_markdown"]
    assert [fake_llm.count(p) for p in ("BriefPartOne", "BriefPartTwo", "BriefPartThree")] == [1, 1, 1]


def test_validator_revises_without_llm_when_deterministic_checks_fail(debated, fake_llm):
    state = debated | brief_writer_node(debated) | {"brief_revision_count": 0}
    state["brief"]["research_findings"]["apps_and_feedback"][0]["evidence_ids"] = ["ev_999"]
    out = brief_validator_node(state)
    assert out["brief_validation"]["verdict"] == "revise"
    assert out["brief_revision_count"] == 1 and out["status"] == "writing_brief"
    assert fake_llm.count("BriefReview") == 0


def test_writer_revision_gets_previous_draft_and_issues(debated, fake_llm):
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return S.BriefPartOne(**build_brief(system, user).model_dump(include=set(S.BriefPartOne.model_fields)))
    fake_llm.overrides[S.BriefPartOne] = capture
    state = debated | brief_writer_node(debated)
    state["brief"]["research_findings"]["apps_and_feedback"][0]["evidence_ids"] = ["ev_999"]
    state |= brief_validator_node(state)
    out = brief_writer_node(state)
    assert "REVISION" in seen["system"] and "<previous_draft>" in seen["user"] and "ev_999" in seen["user"]
    assert out["brief"]["revision"] == 1


def test_revision_cap_approves_with_open_issues(debated, fake_llm):
    state = debated | brief_writer_node(debated) | {"brief_revision_count": 2}      # max_brief_revisions = 2
    state["brief"]["research_findings"]["apps_and_feedback"][0]["evidence_ids"] = ["ev_999"]
    out = brief_validator_node(state)
    v = out["brief_validation"]
    assert v["verdict"] == "approve" and fake_llm.count("BriefReview") == 1
    assert any("det_known_evidence_ids" in i for i in v["open_issues"])
    assert "Validation notes" in out["brief_markdown"]
    assert any(q.startswith("Open brief issue: det_known_evidence_ids") for q in out["unresolved_questions"])


def test_high_severity_llm_failure_revises(debated, fake_llm):
    def failing(system, user):
        r = build_brief_review(system, user)
        r.checks[1] = S.BriefCheck(check_id="solution_not_a_copy", passed=False, severity="high",
                                   issue="Copies app X.", fix_instruction="Name the gap it closes.")
        return r
    fake_llm.overrides[S.BriefReview] = failing
    state = debated | brief_writer_node(debated) | {"brief_revision_count": 0}
    out = brief_validator_node(state)
    assert out["brief_validation"]["verdict"] == "revise"
    failed = [c for c in out["brief_validation"]["checks"] if not c["passed"]]
    assert [c["check_id"] for c in failed] == ["solution_not_a_copy"] and failed[0]["source"] == "llm"


def _asks(system, user):
    return build_brief_review(system, user).model_copy(update={
        "needs_user_input": True, "clarification_questions": ["Must it work offline?"]})


def test_clarify_route_when_a_loop_is_allowed(debated, fake_llm):
    fake_llm.overrides[S.BriefReview] = _asks
    state = debated | brief_writer_node(debated) | {"debate_round": 1, "research_retry_count": 0, "clarification_round_count": 1}
    out = brief_validator_node(state)
    assert out["brief_validation"]["verdict"] == "clarify"
    assert out["brief_validation"]["clarification_questions"] == ["Must it work offline?"]
    assert out["research_retry_count"] == 1 and out["brief_revision_count"] == 0


def test_no_clarify_when_loops_are_exhausted(debated, fake_llm):
    fake_llm.overrides[S.BriefReview] = _asks
    state = debated | brief_writer_node(debated) | {"debate_round": 2}            # max_debate_rounds = 2
    out = brief_validator_node(state)
    v = out["brief_validation"]
    assert v["verdict"] == "approve" and v["clarification_questions"] == []
    assert "Question for you: Must it work offline?" in v["open_issues"]


# --- whole graph -----------------------------------------------------------------------------------------------

def test_pipeline_ends_with_an_approved_brief(debated):
    assert debated["status"] == "completed"
    assert debated["brief_validation"]["verdict"] == "approve"
    assert all(f"## {t}" in debated["brief_markdown"] for t in SECTION_TITLES.values())


def test_pipeline_validator_clarify_loops_back_to_the_user(graph, fake_llm, fake_search):
    calls = {"n": 0}

    def ask_once(system, user):
        calls["n"] += 1
        return _asks(system, user) if calls["n"] == 1 else build_brief_review(system, user)
    fake_llm.overrides[S.BriefReview] = ask_once
    prompts = []

    def clarifier(system, user):
        prompts.append(user)
        return build_clarification(system, user)
    fake_llm.overrides[S.ClarificationResult] = clarifier
    config = {"configurable": {"thread_id": "brief-clarify"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    first = graph.get_state(config).interrupts[0].value["questions"]
    graph.invoke(Command(resume={"answers": {q: "x" for q in first}}), config)
    # the validator asked: the graph went back to clarification. The fake clarifier only asks in round 0, so the
    # validator's question reaches the user only through a real LLM; here we check the loop and its bookkeeping.
    result = graph.get_state(config).values
    assert result["status"] == "completed"
    assert fake_llm.count("BriefReview") == 2 and fake_llm.count("BriefPartOne") == 2
    assert fake_llm.count("ResearchPlan") == 2 and result["research_retry_count"] == 1
    assert result["brief_validation"]["verdict"] == "approve"
    assert "Must it work offline?" in tag("brief_questions", prompts[-1])     # the clarifier saw the question
