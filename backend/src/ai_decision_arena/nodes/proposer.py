"""Node 4 — Proposer: build 2-3 care plans PER PERSPECTIVE from that perspective's evidence.

Three LLM calls run in parallel (one per lane). Each lane only sees its own evidence, so the
"doctor" plans really come from clinical sources and the "patient" plans from patient reports.
Python assigns plan ids (research_a, doctor_b, ...) and checks that cited evidence ids exist.

Quick (patient chat) sessions ask for ONE plan per lane (QUICK_RULE), the main lever for a ~30 s onboarding.

Writes (owner): care_plans, proposer_notes, proposer_lane_status, debate_round, status, current_node.
Also clears criticisms/scores (a new round invalidates the old ones).
"""

import json

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, criticisms_block, evidence_block, perspective_label, user_case_block
from ai_decision_arena.schemas import PERSPECTIVES, CarePlan, ProposerOutput
from ai_decision_arena.state import ArenaState

MAX_PLANS_PER_PERSPECTIVE = 3
PLAN_LETTERS = "abc"

SYSTEM_PROMPT = """You are the Proposer agent of Health Decision Arena. You write plans for ONE lens only:
the {perspective_label}.

From the evidence below, build 2-3 MEANINGFULLY DIFFERENT ways this user could manage their condition,
as this perspective sees it. Each plan must describe: daily routine, diet, medications/treatments as the
evidence reports them, how long until progress is typically seen, whether the condition is common or rare
and the outlook, benefits, drawbacks/risks, assumptions, difficulty, safety notes, supporting evidence ids
and evidence gaps.

Rules:
- Use ONLY the evidence given. Cite evidence ids exactly as given (e.g. "ev_004"). Never cite an id that is
  not in the list, and never present outside knowledge as evidence. If you rely on general knowledge, put
  it in assumptions and say so.
- Tailor every plan to the user's profile, symptoms, goals and constraints (diet, budget, preferences).
- Patient lens: describe what patients REPORT worked or did not work, with how many people / how recurring;
  do not turn anecdotes into recommendations.
- Research lens: prefer stronger evidence (reviews, trials) and say how strong it is.
- Doctor lens: follow guideline-style guidance and say when a clinician's input is needed.
- Plans must differ in approach (e.g. diet-first vs medication-supported vs lifestyle-intensive), not in wording.
- If the evidence supports only one approach, return 1 plan and explain in why_fewer_than_two.
  If the evidence is too thin for any plan, return an empty list, explain, and set evidence_too_thin to true.
- EMERGENCY RULE: if <risk_flags> is non-empty, do NOT return an empty list. Return exactly ONE plan whose
  first routine item tells the user to seek emergency care now: call the local emergency number or have
  someone take them; never drive themselves. The remaining content is what this lens's evidence says for
  AFTER a clinician has assessed them. Do not anchor on a single diagnosis (e.g. DKA) when the symptoms could
  have other serious causes (e.g. chest pain with fast breathing): describe the symptom pattern and say the
  emergency team will find the cause. Name it "Emergency first: ..." and set evidence_too_thin to false.
  The user must still get all three perspectives.
- If <previous_criticisms> is non-empty this is a new debate round: fix those weaknesses, drop plans that
  cannot be defended, and keep what the critic accepted.
""" + BUILDER_RULES


QUICK_RULE = """QUICK SESSION: this overrides every plan count below and in the output schema. Return exactly ONE
plan (plans list of length 1): the approach from this lens that fits this user best. Set why_fewer_than_two to
"quick session" and evidence_too_thin to false, unless the evidence is too thin for any plan (then an empty
list and evidence_too_thin true).

"""


def _propose_lane(state: ArenaState, perspective: str, round_number: int) -> tuple[list[dict], str, str]:
    """One Proposer call for one lane. Returns (CarePlan dicts, note, lane_status) where lane_status is
    ok | thin (evidence insufficient, research may help) | declined (deliberately no plan) | no_evidence."""
    evidence = [e for e in state.get("evidence", []) if e["perspective"] == perspective]
    if not evidence:
        return [], "No evidence was retrieved for this perspective, so no plan could be built.", "no_evidence"

    previous = [c for c in state.get("criticisms", []) if c["plan_id"].startswith(perspective + "_")]
    user_content = f"""{user_case_block(state)}
{evidence_block(evidence)}
<evidence_gaps>{json.dumps([g for g in state.get("evidence_gaps", []) if g.startswith(f"[{perspective}]")], indent=2)}</evidence_gaps>
<previous_criticisms>{criticisms_block(previous) if previous else "(none)"}</previous_criticisms>
<debate_round>{round_number}</debate_round>"""

    system_prompt = SYSTEM_PROMPT.replace("{perspective_label}", perspective_label(perspective))
    quick = get_settings().session_mode == "quick"
    if quick:
        system_prompt = QUICK_RULE + system_prompt
        user_content += "\n<plans_wanted>exactly 1 (quick session)</plans_wanted>"
    out = call_structured(
        ProposerOutput,
        system_prompt,
        user_content,
        max_tokens=7000,
        run_name=f"proposer_{perspective}_llm",
    )

    known = {e["evidence_id"] for e in evidence}
    plans: list[dict] = []
    for i, p in enumerate(out.plans[:1 if quick else MAX_PLANS_PER_PERSPECTIVE]):
        # Trust boundary: only ids from THIS lane's evidence survive. Dropped ones become a visible gap.
        cited = [eid for eid in p.supporting_evidence_ids if eid in known]
        unknown = [eid for eid in p.supporting_evidence_ids if eid not in known]
        gaps = list(p.evidence_gaps)
        if unknown:
            gaps.append(f"Cited evidence ids not found in this perspective's evidence: {unknown}")
        plan = CarePlan(
            **(p.model_dump() | {"supporting_evidence_ids": cited, "evidence_gaps": gaps}),
            plan_id=f"{perspective}_{PLAN_LETTERS[i]}",
            perspective=perspective,
            round=round_number,
        )
        plans.append(plan.model_dump(mode="json"))

    note = out.why_fewer_than_two.strip() if len(plans) < 2 and not quick else ""
    report("proposer", f"{perspective} lane: {len(plans)} plan(s)" + (f" — {note[:80]}" if note else ""))
    if len(plans) >= 2:
        lane_status = "ok"
    elif out.evidence_too_thin:
        lane_status = "thin"
    else:
        lane_status = "declined" if not plans else "ok"   # one deliberate plan is still a plan
    return plans, note, lane_status


def proposer_node(state: ArenaState) -> dict:
    round_number = state.get("debate_round", 0) + 1
    report("proposer", f"debate round {round_number}: building plans for the 3 lanes in parallel")

    with ContextThreadPoolExecutor(max_workers=len(PERSPECTIVES)) as pool:
        results = list(pool.map(lambda p: _propose_lane(state, p, round_number), PERSPECTIVES))

    plans: list[dict] = []
    notes: dict[str, str] = {}
    lane_status: dict[str, str] = {}
    for perspective, (lane_plans, note, status) in zip(PERSPECTIVES, results):
        plans += lane_plans
        lane_status[perspective] = status
        if note:
            notes[perspective] = note

    return {
        "care_plans": plans,
        "proposer_notes": notes,
        "proposer_lane_status": lane_status,
        "criticisms": [],          # previous round's critique no longer applies
        "scores": [],
        "debate_round": round_number,
        "status": "debating",
        "current_node": "proposer",
    }
