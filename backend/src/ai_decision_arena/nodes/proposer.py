"""Node 4 — Proposer: 2-3 solution proposals from the clarified requirements and ALL the evidence, in ONE call.

Python assigns proposal ids (proposal_a, proposal_b, proposal_c) and checks that cited evidence ids exist.
Quick sessions ask for ONE proposal (QUICK_RULE).

Writes (owner): proposals, proposer_notes, proposer_status, debate_round, status, current_node.
Also clears criticisms/scores (a new round invalidates the old ones).
"""

import json

from ai_decision_arena.config import get_settings
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, criticisms_block, evidence_block, user_case_block
from ai_decision_arena.schemas import ProposerOutput, SolutionProposal
from ai_decision_arena.state import ArenaState

MAX_PROPOSALS = 3
LETTERS = "abc"

SYSTEM_PROMPT = """You are the Proposer agent of an AI application builder. From the clarified requirements and the research
evidence below, design 2-3 MEANINGFULLY DIFFERENT solutions for the user's idea: different in approach or scope
(for example a lean first version vs a differentiated product vs a different platform or architecture), not in wording.

Each solution must state: the specific problem it addresses (from the user's requirements and the research), the
target users, the core features essential for a first version and the enhancements that can wait, the key user
journey, a high-level architecture (frontend, backend, database, external services, AI components or "none"),
technology choices each with a reason, how it does better than the existing alternatives found in the evidence,
benefits, drawbacks and risks, assumptions, build difficulty, feasibility within the user's constraints, security
and privacy notes, the evidence ids it relies on, and evidence gaps.

Rules:
- Use ONLY the evidence given. Cite evidence ids exactly as given (e.g. "ev_004"). Never cite an id that is not in
  the list, and never present outside knowledge as evidence. If you rely on general engineering knowledge, say so
  in assumptions.
- Solve the user's underlying problem: a solution that merely copies an existing app without addressing the gaps
  users complain about is weak.
- Respect the user's constraints (platform, technology preferences, budget, timeline, compliance). Anything the
  user did not confirm goes into assumptions.
- Keep the first version small enough to build and verify; put everything else in future_features.
- Do not invent user numbers, benchmarks, prices or capabilities. If the evidence is thin on a point, say so in
  evidence_gaps instead of guessing.
- If <previous_criticisms> is non-empty this is a new debate round: fix those weaknesses, drop solutions that
  cannot be defended, and keep what the critic accepted.
- If the evidence is too thin for any defensible solution, return an empty list, explain, and set
  evidence_too_thin to true.
""" + BUILDER_RULES

QUICK_RULE = """QUICK SESSION: this overrides every proposal count below and in the output schema. Return exactly ONE
proposal (proposals list of length 1): the approach that fits this user best. Set why_fewer_than_two to
"quick session" and evidence_too_thin to false, unless the evidence is too thin for any proposal (then an empty
list and evidence_too_thin true).

"""


def proposer_node(state: ArenaState) -> dict:
    round_number = state.get("debate_round", 0) + 1
    evidence = state.get("evidence", [])
    base = {"criticisms": [], "scores": [], "debate_round": round_number, "status": "debating", "current_node": "proposer"}
    if not evidence:
        report("proposer", "no evidence was retrieved: nothing to propose")
        return base | {"proposals": [], "proposer_notes": "No evidence was retrieved, so no solution could be proposed.",
                       "proposer_status": "no_evidence"}

    quick = get_settings().session_mode == "quick"
    previous = state.get("criticisms", [])
    user_content = f"""{user_case_block(state)}
{evidence_block(evidence)}
<domain_summaries>{json.dumps(state.get("domain_summaries", {}), indent=1)}</domain_summaries>
<evidence_gaps>{json.dumps(state.get("evidence_gaps", []), indent=1)}</evidence_gaps>
<conflicting_claims>{json.dumps(state.get("conflicting_claims", []), indent=1)}</conflicting_claims>
<previous_criticisms>{criticisms_block(previous) if previous else "(none)"}</previous_criticisms>
<debate_round>{round_number}</debate_round>"""
    system_prompt = (QUICK_RULE if quick else "") + SYSTEM_PROMPT
    report("proposer", f"debate round {round_number}: designing {'one solution' if quick else '2-3 solutions'} "
                       f"from {len(evidence)} evidence records")
    out = call_structured(ProposerOutput, system_prompt, user_content, max_tokens=9000, run_name="proposer_llm")

    known = {e["evidence_id"] for e in evidence}
    proposals: list[dict] = []
    for i, p in enumerate(out.proposals[:1 if quick else MAX_PROPOSALS]):
        # Trust boundary: only ids that exist survive. Dropped ones become a visible gap.
        cited = [eid for eid in p.supporting_evidence_ids if eid in known]
        unknown = [eid for eid in p.supporting_evidence_ids if eid not in known]
        gaps = list(p.evidence_gaps)
        if unknown:
            gaps.append(f"Cited evidence ids not found in the evidence: {unknown}")
        proposal = SolutionProposal(
            **(p.model_dump() | {"supporting_evidence_ids": cited, "evidence_gaps": gaps}),
            proposal_id=f"proposal_{LETTERS[i]}",
            round=round_number,
        )
        proposals.append(proposal.model_dump(mode="json"))

    note = out.why_fewer_than_two.strip() if len(proposals) < 2 and not quick else ""
    if len(proposals) >= 2 or (quick and proposals):
        status = "ok"
    elif out.evidence_too_thin:
        status = "thin"                                # a follow-up search may help
    elif not proposals:
        status = "declined"                            # deliberately nothing to propose
    else:
        status = "ok"                                  # one deliberate proposal is still a proposal
    report("proposer", f"{len(proposals)} proposal(s): " + ", ".join(f"{p['proposal_id']} {p['name'][:40]}" for p in proposals)
                       + (f" — {note[:80]}" if note else ""))
    return base | {"proposals": proposals, "proposer_notes": note, "proposer_status": status}
