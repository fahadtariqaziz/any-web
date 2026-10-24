"""Node 6 — Judge: score every plan on the rubric and pick the best plan PER PERSPECTIVE.

Three LLM calls in parallel (one per lane) return criterion scores + "is this lane's evidence
sufficient?". Python then:
- computes weighted totals from the configured rubric weights (never trusts LLM math),
- picks the winner of each lane (highest weighted total),
- makes the routing decision by combining the lanes AND the loop limits.

Writes (owner): scores, verdict, research_retry_count (+1 when sending the graph back to
research or clarification), status, current_node.
"""

import json

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.config import RUBRIC_DESCRIPTIONS, get_settings
from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import (
    BUILDER_RULES,
    criticisms_block,
    evidence_block,
    perspective_label,
    plans_block,
    user_case_block,
)
from ai_decision_arena.schemas import PERSPECTIVES, PerspectiveJudgement, PlanScore, Verdict
from ai_decision_arena.state import ArenaState

SYSTEM_PROMPT = """You are the Judge agent of Health Decision Arena. You compare the plans written for ONE lens,
the {perspective_label}, and decide which one best fits THIS user.

First write your step-by-step reasoning (the `reasoning` field), then score. Score every plan on each rubric
criterion from 0 to 10 with a one-sentence explanation. The weighted
total is computed by the system afterwards; do not compute it yourself.

<rubric>
{rubric}
</rubric>

Consider: the user's case, each plan, the Critic's points (a verified problem weighs more than a possible
risk), and the evidence (strength, relevance, gaps, conflicts). Scores are a reasoning aid, not truth:
explain them. Be strict on safety: a plan with a serious unaddressed safety risk must not score above 4 on
safety. Reward plans whose medications/treatments are reported by the evidence, not assumed.

If <risk_flags> is non-empty the plans are "emergency first" by design: judge them mainly on whether the
urgent-care guidance is correct, unconditional and easy to follow; the after-assessment content is secondary
and thin evidence for it should lower evidence_quality, not make evidence_sufficient false.

evidence_sufficient: true only if this lens's evidence lets you defend a best plan for this user. If not,
say why and list required_evidence a follow-up search should find (at most 4 items).
clarification_questions: at most 2, and ONLY if the user's answer would change which plan wins; otherwise empty.
""" + BUILDER_RULES


def _rubric_text() -> str:
    weights = get_settings().rubric_weights
    return "\n".join(
        f"- {name} (weight {weight:.2f}): {RUBRIC_DESCRIPTIONS.get(name, '')}" for name, weight in weights.items()
    )


def _judge_lane(state: ArenaState, perspective: str) -> PerspectiveJudgement | None:
    plans = [p for p in state.get("care_plans", []) if p["perspective"] == perspective]
    if not plans:
        return None
    criticisms = [c for c in state.get("criticisms", []) if c["plan_id"].startswith(perspective + "_")]
    user_content = f"""{user_case_block(state)}
{plans_block(plans)}
{criticisms_block(criticisms)}
{evidence_block(state.get("evidence", []), max_excerpt_chars=200)}
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>
<conflicting_claims>{json.dumps(state.get("conflicting_claims", []), indent=1)}</conflicting_claims>"""

    out = call_structured(
        PerspectiveJudgement,
        SYSTEM_PROMPT.replace("{perspective_label}", perspective_label(perspective)).replace("{rubric}", _rubric_text()),
        user_content,
        max_tokens=6000,
        run_name=f"judge_{perspective}_llm",
    )
    report("judge", f"{perspective} lane: scored {len(out.scores)} plan(s), evidence {'sufficient' if out.evidence_sufficient else 'insufficient'}")
    return out


def weighted_total(score: PlanScore, weights: dict[str, float]) -> float:
    return round(sum(weights.get(c.criterion, 0.0) * c.score for c in score.criterion_scores), 2)


def _criterion(score: PlanScore, name: str) -> float:
    return next((c.score for c in score.criterion_scores if c.criterion == name), 0.0)


def judge_node(state: ArenaState) -> dict:
    weights = get_settings().rubric_weights
    condition = state.get("project_name", "the condition")
    known_evidence = {e["evidence_id"] for e in state.get("evidence", [])}
    report("judge", "scoring plans on the rubric (3 lanes in parallel)")

    with ContextThreadPoolExecutor(max_workers=len(PERSPECTIVES)) as pool:
        results = list(pool.map(lambda p: _judge_lane(state, p), PERSPECTIVES))

    scores: list[dict] = []
    winners: dict[str, str] = {}
    status: dict[str, str] = {}
    required: list[str] = []
    questions: list[str] = []
    reasons: list[str] = []

    for perspective, out in zip(PERSPECTIVES, results):
        label = perspective_label(perspective).split(" (")[0]
        if out is None:
            lane_kind = (state.get("proposer_lane_status") or {}).get(perspective, "no_evidence")
            note = (state.get("proposer_notes") or {}).get(perspective, "")
            if lane_kind == "declined":
                # The Proposer had evidence but chose not to build a plan (e.g. emergency first).
                # More research cannot change that, so this lane neither blocks nor loops.
                status[perspective] = "declined"
                reasons.append(f"[{perspective}] Proposer deliberately returned no plan: {note[:300]}")
            else:
                status[perspective] = "no_plans"
                required.append(f"Usable sources for the {label.lower()} on {condition}: routine, diet, medications, timeline.")
                why = "evidence too thin" if lane_kind == "thin" else "no usable evidence"
                reasons.append(f"[{perspective}] No plans ({why} for this perspective).")
            continue

        lane_plan_ids = {p["plan_id"] for p in state.get("care_plans", []) if p["perspective"] == perspective}
        lane_scores: list[PlanScore] = []
        for s in out.scores:
            if s.plan_id not in lane_plan_ids:
                continue   # the LLM scored a plan that does not exist in this lane: ignore
            s.weighted_total = weighted_total(s, weights)
            s.supporting_evidence_ids = [eid for eid in s.supporting_evidence_ids if eid in known_evidence]
            lane_scores.append(s)
        unscored = sorted(lane_plan_ids - {s.plan_id for s in lane_scores})

        if lane_scores:
            # Highest weighted total wins; ties go to the better-evidenced plan.
            best = max(lane_scores, key=lambda s: (s.weighted_total, _criterion(s, "evidence_quality")))
            winners[perspective] = best.plan_id
        scores += [s.model_dump(mode="json") for s in lane_scores]

        sufficient = out.evidence_sufficient and bool(lane_scores)
        status[perspective] = "sufficient" if sufficient else "insufficient"
        if not sufficient:
            required += out.required_evidence or [f"[{perspective}] {out.insufficiency_reason or 'More evidence needed.'}"]
        questions += [q for q in out.clarification_questions
                      if q.strip().lower() not in {x.strip().lower() for x in questions}]   # exact-duplicate guard
        note = f" Unscored plans: {unscored}." if unscored else ""
        reasons.append(f"[{perspective}] {out.comparison}{note}")

    # --- Routing decision: Python has the final say, bounded by the loop limits -----------------
    # limits.loops_allowed applies the debate/research/clarification caps and the session time budget.
    can_debate, can_research, can_clarify, blocked = loops_allowed(state)
    blocking = [p for p, v in status.items() if v in ("insufficient", "no_plans")]   # 'declined' never blocks
    all_sufficient = not blocking
    wants_clarification = bool(questions) and not all_sufficient

    update: dict = {"scores": scores, "current_node": "judge"}
    if all_sufficient:
        decision, status_text = "proceed", "verifying"
        declined = [p for p, v in status.items() if v == "declined"]
        reasons.append("Every perspective that offered a plan has a defensible best plan"
                       + (f" (no plan from: {', '.join(declined)})." if declined else "."))
    elif wants_clarification and can_clarify:
        decision, status_text = "request_clarification", "debating"
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = required + ["The user just answered the Judge's follow-up questions "
                                               "(see <clarification_answers>): re-check what those answers change."]
        reasons.append("The user's answers would change the ranking: asking before researching again.")
    elif can_research:
        decision, status_text = "request_more_research", "researching"
        update["research_retry_count"] = state.get("research_retry_count", 0) + 1
        update["research_focus"] = list(required)
        reasons.append("Evidence is insufficient for at least one perspective: running a focused follow-up search.")
    else:
        decision, status_text = "insufficient_evidence", "verifying"
        reasons.append(f"Evidence remains insufficient and the loop limits are reached ({', '.join(blocked) or 'no loop possible'}): "
                       "continuing with the uncertainty stated.")

    update["verdict"] = Verdict(
        decision=decision,
        reason="\n".join(reasons),
        winning_plan_ids=winners,
        perspective_status=status,
        required_evidence=required,
        clarification_questions=questions,
    ).model_dump(mode="json")
    update["status"] = status_text
    report("judge", f"decision: {decision}; winners: {winners}")
    return update
