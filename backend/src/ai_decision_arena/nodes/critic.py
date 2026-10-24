"""Node 5 — Critic: find the real weaknesses in every proposal.

One LLM call per proposal, in parallel. Each call sees that proposal, the user's requirements and ALL the evidence,
so a proposal can be challenged with findings from any research domain.

Writes (owner): criticisms, status, current_node.
"""

import json

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, evidence_block, proposals_block, user_case_block
from ai_decision_arena.schemas import Criticism
from ai_decision_arena.state import ArenaState

MAX_POINTS_PER_PROPOSAL = 6

SYSTEM_PROMPT = """You are the Critic agent of an AI application builder. You review ONE proposed solution against the user's
requirements and ALL the research evidence.

Find the meaningful weaknesses:
- claims the cited evidence does not support, or that other evidence contradicts,
- requirements or constraints of the user that the solution ignores (missing_requirement, ignores_constraint),
- a solution that merely copies an existing product without addressing the gaps users complain about
  (copies_existing_app),
- technical infeasibility within the constraints, hidden dependencies, a first version too large to build and
  verify (infeasible, scope_too_large),
- security, privacy, reliability or compliance problems,
- weak assumptions presented as facts,
- cases where another approach (or a change to this one) would clearly serve the user better.

Rules:
- Assess independently; do not simply agree with the Proposer. But do not manufacture objections: if the solution
  is sound, say so with few or no points.
- Distinguish demonstrated problems (is_verified_problem = true, backed by evidence_ids) from possible risks (false).
  basis = "evidence" only when evidence_ids are given; otherwise "engineering_judgement".
- Cite evidence ids exactly as given. Never cite an id that is not in the evidence.
- Every point needs an actionable suggested_improvement when one exists.
- Return exactly one criticism for the proposal given, at most {max_points} points, most severe first.
""" + BUILDER_RULES


def _critique(state: ArenaState, proposal: dict) -> dict:
    proposal_id = proposal["proposal_id"]
    user_content = f"""{user_case_block(state)}
{proposals_block([proposal])}
{evidence_block(state.get("evidence", []), max_excerpt_chars=250)}
<conflicting_claims>{json.dumps(state.get("conflicting_claims", []), indent=1)}</conflicting_claims>
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>"""
    out = call_structured(
        Criticism,
        SYSTEM_PROMPT.replace("{max_points}", str(MAX_POINTS_PER_PROPOSAL)),
        user_content,
        max_tokens=5000,
        run_name=f"critic_{proposal_id}_llm",
    )
    out.proposal_id = proposal_id                         # Python owns the identity, whatever the LLM echoed
    known_evidence = {e["evidence_id"] for e in state.get("evidence", [])}
    for point in out.points:
        point.evidence_ids = [eid for eid in point.evidence_ids if eid in known_evidence]
        if not point.evidence_ids:
            point.basis = "engineering_judgement"         # a point without surviving evidence ids is judgement
    out.points = out.points[:MAX_POINTS_PER_PROPOSAL]
    report("critic", f"{proposal_id}: {len(out.points)} point(s) raised")
    return out.model_dump(mode="json")


def critic_node(state: ArenaState) -> dict:
    proposals = state.get("proposals", [])
    if not proposals:
        report("critic", "no proposals to review")
        return {"criticisms": [], "status": "debating", "current_node": "critic"}
    report("critic", f"reviewing {len(proposals)} proposal(s) against all evidence (in parallel)")
    with ContextThreadPoolExecutor(max_workers=len(proposals)) as pool:
        criticisms = list(pool.map(lambda p: _critique(state, p), proposals))
    return {"criticisms": criticisms, "status": "debating", "current_node": "critic"}
