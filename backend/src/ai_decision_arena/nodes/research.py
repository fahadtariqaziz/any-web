"""Node 3 — Research: plan searches, run Tavily, turn results into structured Evidence.

Three domains (apps / papers / tech) share one planner call, run their searches in parallel, and each domain
gets its own extractor call (also in parallel).

Writes (owner): research_plan (consumed: set to None), research_queries, evidence, domain_summaries, research_summary, evidence_gaps,
conflicting_claims, rejected_sources, status, current_node.

On a follow-up pass (Judge asked for more research or new clarification), only the open questions are searched
and new evidence is APPENDED; ids continue (ev_021, ...). research_retry_count is incremented by the node that
sends the graph back here (Judge / Evidence Checker), not by this node (the first pass is not a retry).
"""

from ai_decision_arena.progress import report
from ai_decision_arena.research.extractor import extract_evidence
from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from ai_decision_arena.research.sources import normalize_url
from ai_decision_arena.schemas import DOMAIN_LABELS, DOMAINS, ResearchPlan, SearchHit
from ai_decision_arena.state import ArenaState


def _focus_for_follow_up(state: ArenaState) -> list[str] | None:
    """What a follow-up pass should look for. The node that sent the graph back here (Judge, Evidence Checker or
    the user's review feedback) wrote it to research_focus. None on the first pass."""
    if not state.get("evidence"):
        return None
    focus = list(state.get("research_focus") or [])
    if not focus:   # defensive: should not happen, fall back to the Judge's open questions
        focus = list((state.get("verdict") or {}).get("required_evidence", []))
    return focus or None


def research_node(state: ArenaState) -> dict:
    existing = list(state.get("evidence", []))
    focus = _focus_for_follow_up(state)

    # 1) Claude plans the queries for all three domains (on the first pass usually already done by the clarification
    #    node, in parallel with its last call).
    planned = state.get("research_plan")
    if planned and focus is None:
        plan = ResearchPlan.model_validate(planned)
    else:
        report("research", "planning searches for the 3 domains" + (" (follow-up, focused on the open questions)" if focus else ""))
        plan = plan_queries(state, focus=focus)
    report("research", f"planned {len(plan.queries)} searches; running them in parallel")
    queries = [f"[{q.domain}] {q.query}" for q in plan.queries]

    # 2) Tavily runs them in parallel. Skip URLs we already have evidence for.
    hits, failures = run_searches(plan.queries)
    known = {normalize_url(e["source_url"]) for e in existing}
    hits = [h for h in hits if normalize_url(h.url) not in known]
    report("research", f"{len(hits)} unique results" + (f", {len(failures)} search(es) failed" if failures else "")
           + "; extracting evidence per domain")
    by_domain: dict[str, list[SearchHit]] = {d: [h for h in hits if h.domain == d] for d in DOMAINS}

    gaps = [f"[{f.domain}] Search failed for {f.query!r} ({f.error_type})" for f in failures]
    gaps += [f"[{d}] No search results for {DOMAIN_LABELS[d].split(' (')[0].lower()}" for d in DOMAINS if not by_domain[d]]

    # 3) Claude extracts evidence per domain (skipped for empty domains: never invent evidence).
    if hits:
        out = extract_evidence(state, by_domain, start_number=len(existing) + 1)
    else:
        out = {"evidence": [], "rejected": [], "conflicts": [], "gaps": [], "summaries": {}}
    gaps += out["gaps"]

    # Summaries: per domain (merged with earlier passes) and one combined text for printing.
    summaries = dict(state.get("domain_summaries", {}))
    for d, text in out["summaries"].items():
        summaries[d] = f"{summaries[d]}\n\nFollow-up: {text}" if d in summaries else text
    combined = "\n\n".join(f"## {DOMAIN_LABELS[d]}\n{summaries[d]}" for d in DOMAINS if d in summaries)

    return {
        "research_queries": list(state.get("research_queries", [])) + queries,
        "evidence": existing + out["evidence"],
        "rejected_sources": list(state.get("rejected_sources", [])) + out["rejected"],
        "conflicting_claims": list(state.get("conflicting_claims", [])) + out["conflicts"],
        "evidence_gaps": gaps,     # replaced each pass: these are the CURRENT open gaps
        "domain_summaries": summaries,
        "research_summary": combined or "No evidence was retrieved.",
        "research_focus": [],      # consumed
        "research_plan": None,     # consumed (planned ahead by the clarification node)
        "status": "debating",
        "current_node": "research",
    }
