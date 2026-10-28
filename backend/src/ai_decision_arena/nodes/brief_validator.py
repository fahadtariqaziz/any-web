"""Node 11 — Brief Validator: check the brief before the user sees it (spec §5).

1. Deterministic Python checks first (brief.deterministic_checks): every cited evidence id exists, every verified /
   research_backed statement cites evidence, numeric success targets have a basis, all ten sections are filled,
   no URL that is not in the evidence, the one-page word budget. They fail hard: if one fails and a revision is
   left, the brief goes straight back to the writer (no LLM call).
2. Otherwise ONE LLM call reviews the nine criteria of spec §5 (BriefReview).
3. Python decides (never the LLM):
   - clarify  → clarification: the reviewer says critical information is missing or the requirements contradict
                each other, AND a clarification loop is allowed (limits.loops_allowed);
   - revise   → brief_writer: a deterministic check failed, a high-severity criterion failed, or at least
                MEDIUM_FAILURES_TO_REVISE medium ones did, AND brief_revision_count < max_brief_revisions;
                fast path (auto_loops=false): medium failures never revise (they become open issues) and at most
                one rewrite;
   - approve  → the brief goes to the user's review (await_brief_review). Failed checks that could
                not be fixed are listed as open issues: as validation notes at the end of the brief's section 9 and
                in unresolved_questions.

Writes (owner): brief_validation, brief_revision_count, brief_markdown (re-rendered with open issues),
unresolved_questions, research_retry_count + research_focus (clarify), status, current_node.
"""

from ai_decision_arena.brief import WORD_BUDGET_TOLERANCE, deterministic_checks, render_brief_markdown
from ai_decision_arena.config import get_settings
from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.llm import call_structured
from ai_decision_arena.nodes.brief_writer import brief_alternatives
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, evidence_block, user_case_block
from ai_decision_arena.schemas import BRIEF_CHECK_IDS, BriefReview, BriefValidation, ProblemBrief, ValidationCheck
from ai_decision_arena.state import ArenaState

MAX_QUESTIONS = 2
MEDIUM_FAILURES_TO_REVISE = 2      # one medium weakness goes forward as an open issue; two or more cost a rewrite

SYSTEM_PROMPT = """You are the Brief Validator of an AI application builder. You check the problem statement and solution
brief BEFORE the user sees it. Be strict but fair: fail a check only for a real problem a reader would notice.

Check each criterion (one entry per check id, in this order):
1. problem_clear_and_consistent: the problem is clearly stated, solution-neutral, and consistent with the user's
   clarified requirements (<user_input>, profile, features, constraints).
2. solution_not_a_copy: the solution addresses the identified problem rather than merely copying existing apps.
3. recommendations_supported: major recommendations are supported by the research (cited) or explicitly labelled
   as recommendations / assumptions.
4. technically_plausible: features and architecture are technically plausible within the known constraints.
5. scope_separates_mvp: the scope separates essential (MVP) functionality from optional enhancements.
6. success_criteria_measurable: success criteria are measurable where possible and contain no fabricated targets
   (a number needs a baseline from the user or the evidence).
7. risks_and_questions_disclosed: important risks, dependencies and unresolved questions are disclosed.
8. claims_have_sources: research claims cite supporting sources wherever possible (labels in the text say
   verified / research with reference numbers; check them against <evidence>).
9. concise_consistent_readable: concise, internally consistent, and understandable to technical and non-technical
   readers. Length: <main_part_words> is the word count of sections 1-9 (labels and citations not counted) and
   <word_limit> the limit for about one page; at or under the limit the length is fine, do not fail it for length. The appendix is supplementary and
   does not count toward the page, but flag it if it mostly repeats the main part or contradicts it.

severity: high = the brief would mislead the user or cannot be planned from; medium = a clear weakness; low =
polish. Keep each issue to at most 2 short sentences and each fix_instruction to one; leave both empty when the
check passes.

needs_user_input: true ONLY when critical information is missing or the user's requirements contradict each other
so that no rewrite can fix it; then ask at most 2 short questions the user can answer. Questions already in
<clarification_answers> must not be asked again. A brief that lists an open question is NOT by itself a reason to
ask: ask only if the brief cannot responsibly go forward without the answer.

<deterministic_checks> are Python checks already run on the brief; do not repeat them.
""" + BUILDER_RULES


def _review(state: ArenaState, markdown: str, det: list[ValidationCheck], words: int, budget: int) -> BriefReview:
    det_lines = "\n".join(f"- {c.check_id}: {'passed' if c.passed else 'FAILED: ' + c.issue}" for c in det)
    user = f"""{user_case_block(state)}
<brief>
{markdown}
</brief>
<deterministic_checks>
{det_lines}
</deterministic_checks>
<main_part_words>{words}</main_part_words>
<word_limit>{int(budget * WORD_BUDGET_TOLERANCE)}</word_limit>
<check_order>{", ".join(BRIEF_CHECK_IDS)}</check_order>
{evidence_block(state.get("evidence", []), max_excerpt_chars=200)}"""
    return call_structured(BriefReview, SYSTEM_PROMPT, user, max_tokens=7000, run_name="brief_validator_llm",
                           model=get_settings().validator_model)


def brief_validator_node(state: ArenaState) -> dict:
    settings = get_settings()
    brief = ProblemBrief.model_validate(state["brief"])
    evidence = state.get("evidence", [])
    alternatives = brief_alternatives(state)
    markdown, words = render_brief_markdown(brief, alternatives, word_budget=settings.brief_word_budget)
    revisions_used = state.get("brief_revision_count", 0)
    # Fast path: one rewrite at most (measured: further rounds did not converge, 13/15 → 12/15 → 13/15 checks passed).
    max_revisions = settings.max_brief_revisions if settings.auto_loops else min(settings.max_brief_revisions, 1)
    can_revise = revisions_used < max_revisions
    _, _, can_clarify, blocked = loops_allowed(state)

    det = deterministic_checks(brief, evidence, words, settings.brief_word_budget)
    det_failed = [c for c in det if not c.passed]
    report("brief_validator", f"deterministic checks: {len(det) - len(det_failed)} of {len(det)} passed"
           + (f" (failed: {', '.join(c.check_id for c in det_failed)})" if det_failed else ""))

    update: dict = {"current_node": "brief_validator"}
    checks = list(det)
    questions: list[str] = []
    llm_summary = ""

    if det_failed and can_revise:
        verdict, reason = "revise", "Deterministic checks failed; the writer fixes them before the review."
    else:
        report("brief_validator", "reviewing the brief against the nine validation criteria")
        review = _review(state, markdown, det, words, settings.brief_word_budget)
        llm_summary = review.summary
        checks += [ValidationCheck(check_id=c.check_id, source="llm", passed=c.passed,
                                   severity="low" if c.passed else c.severity,
                                   issue="" if c.passed else c.issue,
                                   fix_instruction="" if c.passed else c.fix_instruction) for c in review.checks]
        answered = {q.strip().lower() for q in state.get("clarification_answers", {})}
        for q in review.clarification_questions:
            q = q.strip()
            if q and q.lower() not in answered and q.lower() not in {x.lower() for x in questions}:
                questions.append(q)
        questions = questions[:MAX_QUESTIONS]
        high = [c for c in checks if c.source == "llm" and not c.passed and c.severity == "high"]
        medium = [c for c in checks if c.source == "llm" and not c.passed and c.severity == "medium"]
        if len(medium) >= MEDIUM_FAILURES_TO_REVISE and settings.auto_loops:
            high += medium                       # several medium weaknesses together are worth a rewrite
        if review.needs_user_input and questions and can_clarify:
            verdict, reason = "clarify", "Critical information is missing or contradictory: asking the user before continuing."
        elif (det_failed or high) and can_revise:
            verdict, reason = "revise", f"{len(det_failed) + len(high)} check(s) failed with high impact: revising the brief."
        else:
            verdict = "approve"
            reason = "The brief passed validation." if not (det_failed or high) else (
                "Some checks still fail but no revision is left: the brief goes forward with them listed as open issues.")
            if review.needs_user_input and questions and not can_clarify:
                reason += f" Questions for the user could not be asked ({', '.join(blocked) or 'no clarification round left'})."

    passed = sum(1 for c in checks if c.passed)
    open_issues: list[str] = []
    if verdict == "approve":
        open_issues = [f"{c.check_id}: {c.issue}" for c in checks if not c.passed and c.severity in ("medium", "high")]
        open_issues += [f"Question for you: {q}" for q in questions]
        if open_issues and reason == "The brief passed validation.":
            reason = (f"No blocking problem; {len(open_issues)} medium issue(s) are listed as validation notes at the "
                      "end of the brief.")
        if open_issues:
            update["brief_markdown"], _ = render_brief_markdown(brief, alternatives, open_issues, settings.brief_word_budget)
            unresolved = list(state.get("unresolved_questions", []))
            update["unresolved_questions"] = unresolved + [f"Open brief issue: {i}" for i in open_issues
                                                           if f"Open brief issue: {i}" not in unresolved]
        update["status"] = "awaiting_brief_review"
    elif verdict == "revise":
        update["brief_revision_count"] = revisions_used + 1
        update["status"] = "writing_brief"
    else:   # clarify: back to the clarification node with the questions; the brief is rewritten afterwards
        update["brief_revision_count"] = 0
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = [f"The user answered questions the brief validator asked ({'; '.join(questions)}): "
                                    "re-check what those answers change."]
        update["status"] = "validating_brief"

    update["brief_validation"] = BriefValidation(
        verdict=verdict, reason=reason, revision=brief.revision, brief_generated_at=brief.generated_at, checks=checks, word_count=words,
        word_budget=settings.brief_word_budget, clarification_questions=questions if verdict == "clarify" else [],
        open_issues=open_issues, llm_summary=llm_summary,
    ).model_dump(mode="json")
    report("brief_validator", f"decision: {verdict}; {passed} of {len(checks)} checks passed")
    return update
