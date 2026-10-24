"""Node 7 — Evidence Checker: do the winning plans' claims really follow from the cited evidence?

One LLM call per winning plan (three lanes in parallel). The checker sees the plan, the evidence it
cites IN FULL, the rest of its lane's evidence in compact form, and the Critic's points. It returns a
verdict per claim (verified / partially_supported / unsupported / contradicted / irrelevant /
unavailable) and the MATERIAL gaps (claims whose failure would change the guidance).

Python then:
- stores ClaimVerification records and updates evidence[].verification_status,
- decides routing: material gaps + loops allowed → one focused research pass; otherwise → the final report,
  with the gaps recorded as unresolved questions (never hidden).

Writes (owner): verification_results, checker_verdict, evidence[].verification_status,
unresolved_questions (append), research_focus / research_retry_count (when looping), status, current_node.
"""

from langsmith.utils import ContextThreadPoolExecutor

from ai_decision_arena.limits import loops_allowed
from ai_decision_arena.llm import call_structured
from ai_decision_arena.progress import report
from ai_decision_arena.prompting import SAFETY_RULES, criticisms_block, evidence_block, perspective_label, plans_block, user_case_block
from ai_decision_arena.schemas import PERSPECTIVES, ClaimVerification, PlanVerification
from ai_decision_arena.state import ArenaState

MAX_CLAIMS = 10
STATUS_RANK = {"contradicted": 0, "unsupported": 1, "irrelevant": 2, "partially_supported": 3, "verified": 4}

SYSTEM_PROMPT = """You are the Evidence Checker of Health Decision Arena. You verify the factual claims of ONE care plan,
written from the {perspective_label}, against the evidence it cites.

For each checkable factual claim in the plan (effects, numbers, guidance attributed to sources, timelines,
prevalence, what patients reported) decide:
- verified: the cited excerpt says this.
- partially_supported: the excerpt supports part of it, or a weaker version.
- unsupported: the cited evidence does not say this, and nothing else in the evidence given does.
- contradicted: the evidence says the opposite.
- irrelevant: the cited evidence is about something else.
- unavailable: the claim cites no evidence, or ids that are not in the list.

Rules:
- Judge ONLY from the evidence text given here. An official or popular source does not make a claim
  verified; the excerpt itself must support it.
- Instructions such as "seek emergency care", "discuss with your doctor" or "do not change medication"
  are safety guidance, not claims to verify. Skip them.
- is_anecdotal: true when the only support is individual patient reports.
- is_material: true if what the user is told to do would change were this claim wrong.
- At most {max_claims} claims, most important first. material_gaps: for each MATERIAL claim that is
  unsupported, contradicted or unavailable, what a follow-up search should look for; empty list if none.
""" + SAFETY_RULES


def _check_lane(state: ArenaState, perspective: str, plan: dict) -> PlanVerification:
    lane_evidence = [e for e in state.get("evidence", []) if e["perspective"] == perspective]
    cited_ids = set(plan.get("supporting_evidence_ids", []))
    cited = [e for e in lane_evidence if e["evidence_id"] in cited_ids]
    others = [e for e in lane_evidence if e["evidence_id"] not in cited_ids]
    criticisms = [c for c in state.get("criticisms", []) if c["plan_id"] == plan["plan_id"]]
    user_content = f"""{user_case_block(state)}
{plans_block([plan])}
<cited_evidence>
{evidence_block(cited, max_excerpt_chars=700)}
</cited_evidence>
<other_evidence_in_this_lane>
{evidence_block(others, max_excerpt_chars=200)}
</other_evidence_in_this_lane>
{criticisms_block(criticisms)}"""
    out = call_structured(
        PlanVerification,
        SYSTEM_PROMPT.replace("{perspective_label}", perspective_label(perspective)).replace("{max_claims}", str(MAX_CLAIMS)),
        user_content,
        max_tokens=5000,
        run_name=f"evidence_checker_{perspective}_llm",
    )
    counts = {}
    for c in out.claims:
        counts[c.status] = counts.get(c.status, 0) + 1
    report("evidence_checker", f"{perspective} lane: {len(out.claims)} claim(s) checked "
                               + ", ".join(f"{k} {v}" for k, v in counts.items())
                               + (f"; {len(out.material_gaps)} material gap(s)" if out.material_gaps else ""))
    return out


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
    winners = (state.get("verdict") or {}).get("winning_plan_ids", {})
    plans = {p["plan_id"]: p for p in state.get("care_plans", [])}
    lanes = [(p, plans[winners[p]]) for p in PERSPECTIVES if p in winners and winners[p] in plans]
    known_ids = {e["evidence_id"] for e in state.get("evidence", [])}
    report("evidence_checker", f"verifying {len(lanes)} winning plan(s) against the evidence they cite (in parallel)")

    with ContextThreadPoolExecutor(max_workers=max(1, len(lanes))) as pool:
        outputs = list(pool.map(lambda item: _check_lane(state, *item), lanes))

    results: list[dict] = []
    gaps_by_lane: dict[str, list[str]] = {}
    summaries: dict[str, str] = {}
    by_evidence: dict[str, list[str]] = {}
    for (perspective, plan), out in zip(lanes, outputs):
        for c in out.claims[:MAX_CLAIMS]:
            ids = [i for i in c.evidence_ids if i in known_ids]
            status = c.status if (ids or c.status == "unavailable") else "unavailable"   # cites nothing real
            results.append(ClaimVerification(
                claim=c.claim, plan_id=plan["plan_id"], perspective=perspective, evidence_ids=ids,
                status=status, notes=c.notes, is_anecdotal=c.is_anecdotal, is_material=c.is_material,
            ).model_dump(mode="json"))
            for i in ids:
                by_evidence.setdefault(i, []).append(status)
        if out.material_gaps:
            gaps_by_lane[perspective] = out.material_gaps
        summaries[perspective] = out.overall

    # Evidence records get a verification status (the Research node set "pending").
    evidence = [
        dict(e, verification_status=_evidence_status(by_evidence.get(e["evidence_id"], [])))
        if e["evidence_id"] in by_evidence else e
        for e in state.get("evidence", [])
    ]

    can_debate, can_research, _, blocked = loops_allowed(state)
    gaps = [f"[{lane}] {gap}" for lane, items in gaps_by_lane.items() for gap in items]
    update: dict = {
        "verification_results": results,
        "evidence": evidence,
        "current_node": "evidence_checker",
    }
    if gaps and can_research:
        decision = "request_more_research"
        reason = "Material claims of a winning plan are not supported by the cited evidence: one focused research pass."
        update |= {
            "research_focus": gaps,
            "research_retry_count": state.get("research_retry_count", 0) + 1,
            "status": "researching",
        }
    else:
        decision = "proceed"
        reason = ("All material claims are supported." if not gaps else
                  f"Unverified material claims remain ({'; '.join(blocked) or 'no loop possible'}); "
                  "continuing with them listed as unresolved.")
        unresolved = list(state.get("unresolved_questions", []))
        unresolved += [f"Unverified: {g}" for g in gaps if f"Unverified: {g}" not in unresolved]
        update |= {"unresolved_questions": unresolved, "status": "reporting"}

    update["checker_verdict"] = {
        "decision": decision, "reason": reason, "gaps_by_lane": gaps_by_lane, "summaries": summaries,
        "claims_checked": len(results),
    }
    report("evidence_checker", f"decision: {decision}")
    return update
