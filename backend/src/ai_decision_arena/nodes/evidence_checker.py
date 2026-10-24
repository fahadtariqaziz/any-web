"""Node 7 — Evidence Checker: do the winning proposal's claims really follow from the cited evidence?

One LLM call for the winning proposal. The checker sees the proposal, the evidence it cites IN FULL, the rest of the
evidence in compact form, and the Critic's points. It returns a verdict per claim (verified / partially_supported /
unsupported / contradicted / irrelevant / unavailable) and the MATERIAL gaps (claims whose failure would change the
design).

Python then:
- stores ClaimVerification records and updates evidence[].verification_status,
- decides routing: material gaps + loops allowed → one focused research pass; otherwise → the report, with the
  gaps recorded as unresolved questions (never hidden).

Writes (owner): verification_results, checker_verdict, evidence[].verification_status, unresolved_questions
(append), research_focus / research_retry_count (when looping), status, current_node.
"""

from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import BUILDER_RULES, criticisms_block, evidence_block, proposals_block, user_case_block
from ai_decision_arena.schemas import ClaimVerification, ProposalVerification
from ai_decision_arena.state import ArenaState

MAX_CLAIMS = 10
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


def evidence_checker_node(state: ArenaState) -> dict:
    winner_id = (state.get("verdict") or {}).get("winning_proposal_id")
    proposals = {p["proposal_id"]: p for p in state.get("proposals", [])}
    if not winner_id or winner_id not in proposals:
        report("evidence_checker", "no winning proposal to verify")
        return {
            "verification_results": [],
            "checker_verdict": {"decision": "proceed", "reason": "No winning proposal to verify.", "material_gaps": [],
                                "summary": "", "claims_checked": 0},
            "status": "reporting",
            "current_node": "evidence_checker",
        }

    proposal = proposals[winner_id]
    evidence = state.get("evidence", [])
    cited_ids = set(proposal.get("supporting_evidence_ids", []))
    cited = [e for e in evidence if e["evidence_id"] in cited_ids]
    others = [e for e in evidence if e["evidence_id"] not in cited_ids]
    criticisms = [c for c in state.get("criticisms", []) if c["proposal_id"] == winner_id]
    report("evidence_checker", f"verifying {winner_id} against the {len(cited)} evidence record(s) it cites")
    user_content = f"""{user_case_block(state)}
{proposals_block([proposal])}
<cited_evidence>
{evidence_block(cited, max_excerpt_chars=700)}
</cited_evidence>
<other_evidence>
{evidence_block(others, max_excerpt_chars=200)}
</other_evidence>
{criticisms_block(criticisms)}"""
    out = call_structured(
        ProposalVerification,
        SYSTEM_PROMPT.replace("{max_claims}", str(MAX_CLAIMS)),
        user_content,
        max_tokens=5000,
        run_name="evidence_checker_llm",
    )

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
    report("evidence_checker", f"{winner_id}: {len(results)} claim(s) checked "
                               + ", ".join(f"{k} {v}" for k, v in counts.items())
                               + (f"; {len(out.material_gaps)} material gap(s)" if out.material_gaps else ""))

    # Evidence records get a verification status (the Research node set "pending").
    evidence = [
        dict(e, verification_status=_evidence_status(by_evidence.get(e["evidence_id"], [])))
        if e["evidence_id"] in by_evidence else e
        for e in evidence
    ]

    can_debate, can_research, _, blocked = loops_allowed(state)
    gaps = list(out.material_gaps)
    update: dict = {"verification_results": results, "evidence": evidence, "current_node": "evidence_checker"}
    if gaps and can_research:
        decision = "request_more_research"
        reason = "Material claims of the winning proposal are not supported by the cited evidence: one focused research pass."
        update |= {"research_focus": gaps, "research_retry_count": state.get("research_retry_count", 0) + 1,
                   "status": "researching"}
    else:
        decision = "proceed"
        reason = ("All material claims are supported." if not gaps else
                  f"Unverified material claims remain ({'; '.join(blocked) or 'no loop possible'}); "
                  "continuing with them listed as unresolved.")
        unresolved = list(state.get("unresolved_questions", []))
        unresolved += [f"Unverified: {g}" for g in gaps if f"Unverified: {g}" not in unresolved]
        update |= {"unresolved_questions": unresolved, "status": "reporting"}

    update["checker_verdict"] = {"decision": decision, "reason": reason, "material_gaps": gaps, "summary": out.overall,
                                 "claims_checked": len(results)}
    report("evidence_checker", f"decision: {decision}")
    return update
