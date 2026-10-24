"""Node 5 — Critic: find the real weaknesses in every care plan.

Three LLM calls in parallel (one per lane). The Critic of a lane sees that lane's plans but
ALL evidence, so a patient plan can be challenged with research findings and vice versa.

Writes (owner): criticisms, status, current_node.
"""

import json

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import SAFETY_RULES, evidence_block, perspective_label, plans_block, user_case_block
from ai_decision_arena.schemas import PERSPECTIVES, Criticism, CriticOutput
from ai_decision_arena.state import ArenaState

MAX_POINTS_PER_PLAN = 6

SYSTEM_PROMPT = """You are the Critic agent of Health Decision Arena. You review the plans written for the
{perspective_label}, and you may use evidence from ALL perspectives to challenge them.

For each plan, find the meaningful weaknesses:
- safety risks, interactions or contraindications given this user's profile and medications,
- claims the cited evidence does not actually support, or that other evidence contradicts,
- advice resting only on anecdotes, or on outdated guidance,
- parts that ignore the user's constraints, symptoms or goals (not_fit_for_user),
- important missing considerations, and parts that are unrealistic to follow,
- cases where another plan (or a change to this one) would clearly serve the user better.

Rules:
- Assess independently; do not simply agree with the Proposer. But do not manufacture objections:
  if a plan is sound, say so with few or no points.
- Distinguish demonstrated problems (is_verified_problem = true, backed by evidence_ids) from possible
  risks (false). basis = "evidence" only when evidence_ids are given; otherwise "clinical_reasoning".
- Cite evidence ids exactly as given. Never cite an id that is not in the evidence.
- Every point needs an actionable suggested_improvement when one exists.
- If <red_flags> is non-empty, a plan that puts urgent care first is correct; do not criticise it for
  being a single plan. Check that its urgency is unconditional and critique the after-assessment content.
- Return exactly one criticism per plan, at most {max_points} points each, most severe first.
""" + SAFETY_RULES


def _critique_lane(state: ArenaState, perspective: str) -> list[dict]:
    plans = [p for p in state.get("care_plans", []) if p["perspective"] == perspective]
    if not plans:
        return []

    user_content = f"""{user_case_block(state)}
{plans_block(plans)}
{evidence_block(state.get("evidence", []), max_excerpt_chars=250)}
<conflicting_claims>{json.dumps(state.get("conflicting_claims", []), indent=1)}</conflicting_claims>
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>"""

    out = call_structured(
        CriticOutput,
        SYSTEM_PROMPT.replace("{perspective_label}", perspective_label(perspective))
                     .replace("{max_points}", str(MAX_POINTS_PER_PLAN)),
        user_content,
        max_tokens=6000,
        run_name=f"critic_{perspective}_llm",
    )

    known_evidence = {e["evidence_id"] for e in state.get("evidence", [])}
    by_plan = {c.plan_id: c for c in out.criticisms}
    criticisms: list[dict] = []
    for plan in plans:
        c = by_plan.get(plan["plan_id"])
        if c is None:   # Python guarantees one entry per plan, even if the LLM skipped one
            c = Criticism(plan_id=plan["plan_id"], points=[], overall_assessment="Not assessed by the Critic.")
        for point in c.points:
            point.evidence_ids = [eid for eid in point.evidence_ids if eid in known_evidence]
            if not point.evidence_ids:
                point.basis = "clinical_reasoning"   # a claim without surviving evidence ids is reasoning
        c.points = c.points[:MAX_POINTS_PER_PLAN]
        criticisms.append(c.model_dump(mode="json"))
    report("critic", f"{perspective} lane: reviewed {len(plans)} plan(s), {sum(len(c['points']) for c in criticisms)} point(s) raised")
    return criticisms


def critic_node(state: ArenaState) -> dict:
    report("critic", "reviewing every plan against all evidence (3 lanes in parallel)")
    with ContextThreadPoolExecutor(max_workers=len(PERSPECTIVES)) as pool:
        results = list(pool.map(lambda p: _critique_lane(state, p), PERSPECTIVES))
    return {
        "criticisms": [c for lane in results for c in lane],
        "status": "debating",
        "current_node": "critic",
    }
