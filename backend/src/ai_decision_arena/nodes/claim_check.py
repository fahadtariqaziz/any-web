"""Claim check: do a proposal's factual claims really follow from the evidence it cites?

Not a graph node (review of 2026-10-29: the separate Evidence Checker node was folded into the Judge). Two parts:
- `verify_proposal`: ONE LLM call for ONE proposal, run by the CRITIC node for every proposal, in parallel with the
  critiques (speed: the check never waits for the judge). It sees the proposal, the evidence it cites IN FULL and the
  rest of the evidence in compact form, and returns a verdict per claim (verified / partially_supported / unsupported /
  contradicted / irrelevant / unavailable) and the MATERIAL gaps (claims whose failure would change the design).
- `consolidate`: pure Python, run by the JUDGE once the winner is known: takes the winner's stored check (or makes the
  call when a state from before the critic's pool has none), keeps only evidence ids that exist, stores one
  ClaimVerification per claim, and sets evidence[].verification_status. The Judge then folds the material gaps into
  its ONE routing decision (research pass when a loop is allowed, else open questions in the brief).
"""

from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, evidence_block, proposals_block, user_case_block
from ai_decision_arena.schemas import ClaimVerification, ProposalVerification
from ai_decision_arena.state import ArenaState

MAX_CLAIMS = 6                         # the most important claims (speed: fewer output tokens)
STATUS_RANK = {"contradicted": 0, "unsupported": 1, "irrelevant": 2, "partially_supported": 3, "verified": 4}

SYSTEM_PROMPT = """You are the Evidence Checker of an AI application builder. You verify the factual claims of ONE proposed
solution against the evidence it cites.

For each checkable factual claim in the proposal (what existing products do or lack, what users complain about,
what a library, API or framework can do, research findings, numbers, limitations) decide:
- verified: the cited excerpt says this.
- partially_supported: the excerpt supports part of it, or a weaker version.
- unsupported: the cited evidence does not say this, and nothing else in the evidence given does.
- contradicted: the evidence says the opposite.
- irrelevant: the cited evidence is about something else.
- unavailable: the claim cites no evidence, or ids that are not in the list.

Rules:
- Judge ONLY from the evidence text given here. An official or popular source does not make a claim verified; the
  excerpt itself must support it.
- Design decisions and recommendations ("use React", "keep the MVP small") are not claims to verify. Skip them.
- is_anecdotal: true when the only support is individual user reports.
- is_material: true if the proposal's core design would change were this claim wrong.
- At most {max_claims} claims, most important first. material_gaps: for each MATERIAL claim that is unsupported,
  contradicted or unavailable, what a follow-up search should look for; empty list if none.

Where the line goes (examples of the judgement, not of the format):
- Claim "AI categorisation removes all expense errors"; the cited excerpt says "automated categorisation assigns a
  category to each transaction" → unsupported: the excerpt shows the capability, not an error rate. A capability
  never proves an outcome.
- Claim "Users of app X complain that sync loses entries"; the cited excerpts are two forum posts describing lost
  entries after a sync → verified, is_anecdotal true (individual reports, no aggregate).
- Claim "Library Y supports offline use"; the cited excerpt says "Y caches fetched responses for offline reading" →
  partially_supported: a weaker version (read-only caching) is what the source says.
- Claim "The market for budgeting apps is growing 20% a year"; the cited excerpt is a page about the app's pricing →
  irrelevant; if nothing else in the evidence gives a growth figure, the number is unsupported.
- "Use React with Vite for the frontend" → a design decision, not a claim: skip it.
""" + BUILDER_RULES


def _evidence_status(statuses: list[str]) -> str:
    """One status per evidence item from the statuses of the claims that cite it."""
    if not statuses:
        return "pending"
    if "contradicted" in statuses:
        return "contradicted"
    if all(s == "verified" for s in statuses):
        return "verified"
    if "verified" in statuses or "partially_supported" in statuses:
        return "partially_supported"
    return min(statuses, key=lambda s: STATUS_RANK.get(s, 9))


def verify_proposal(state: ArenaState, proposal: dict, node: str = "judge") -> ProposalVerification:
    """One LLM call: the claims of ONE proposal against the evidence it cites (called by the critic node, in parallel
    with the critiques, and as a fallback by the judge when a state has no stored check)."""
    evidence = state.get("evidence", [])
    cited_ids = set(proposal.get("supporting_evidence_ids", []))
    cited = [e for e in evidence if e["evidence_id"] in cited_ids]
    others = [e for e in evidence if e["evidence_id"] not in cited_ids]
    report(node, f"checking the claims of {proposal['proposal_id']} against the {len(cited)} evidence record(s) it cites")
    user_content = f"""{user_case_block(state)}
{proposals_block([proposal])}
<cited_evidence>
{evidence_block(cited, max_excerpt_chars=700)}
</cited_evidence>
<other_evidence>
{evidence_block(others, max_excerpt_chars=200)}
</other_evidence>"""
    return call_structured(
        ProposalVerification,
        SYSTEM_PROMPT.replace("{max_claims}", str(MAX_CLAIMS)),
        user_content,
        max_tokens=5000,
        run_name=f"evidence_checker_{proposal['proposal_id']}_llm",
    )


def consolidate(state: ArenaState, winner_id: str | None, node: str = "judge") -> dict:
    """Python only (unless no stored check exists): the winner's claim check as state fields.
    Returns {verification_results, evidence, material_gaps, summary, claims_checked}; empty results without a winner."""
    proposals = {p["proposal_id"]: p for p in state.get("proposals", [])}
    evidence = state.get("evidence", [])
    if not winner_id or winner_id not in proposals:
        return {"verification_results": [], "evidence": evidence, "material_gaps": [], "summary": "", "claims_checked": 0}

    stored = (state.get("proposal_checks") or {}).get(winner_id)
    if stored is not None:
        report(node, f"using the claim check of {winner_id} made in parallel with the critic")
        out = ProposalVerification.model_validate(stored)
    else:
        out = verify_proposal(state, proposals[winner_id], node)

    known_ids = {e["evidence_id"] for e in evidence}
    results: list[dict] = []
    by_evidence: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for c in out.claims[:MAX_CLAIMS]:
        ids = [i for i in c.evidence_ids if i in known_ids]
        status = c.status if (ids or c.status == "unavailable") else "unavailable"   # cites nothing real
        counts[status] = counts.get(status, 0) + 1
        results.append(ClaimVerification(
            claim=c.claim, proposal_id=winner_id, evidence_ids=ids, status=status, notes=c.notes,
            is_anecdotal=c.is_anecdotal, is_material=c.is_material,
        ).model_dump(mode="json"))
        for i in ids:
            by_evidence.setdefault(i, []).append(status)
    report(node, f"{winner_id}: {len(results)} claim(s) checked "
                 + ", ".join(f"{k} {v}" for k, v in counts.items())
                 + (f"; {len(out.material_gaps)} material gap(s)" if out.material_gaps else ""))

    # Evidence records get a verification status (the Research node set "pending").
    evidence = [
        dict(e, verification_status=_evidence_status(by_evidence.get(e["evidence_id"], [])))
        if e["evidence_id"] in by_evidence else e
        for e in evidence
    ]
    return {"verification_results": results, "evidence": evidence, "material_gaps": list(out.material_gaps),
            "summary": out.overall, "claims_checked": len(results)}
