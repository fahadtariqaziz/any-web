"""Shared terminal printing for the demo scripts, incl. live streaming of graph progress."""

import time

from ai_decision_arena.schemas import DOMAIN_LABELS, DOMAINS


def stream_graph(graph, graph_input, config, shown_risk_flags: set | None = None) -> tuple[dict, dict | None]:
    """Run the graph while printing what is happening:
    - "custom" events = progress lines emitted by nodes while they run (progress.report),
    - "updates"       = one line per finished node, risk flags the moment they are recorded,
    - "values"        = the full state after each step; the last one is returned.
    Returns (final_state_values, interrupt_payload_or_None)."""
    shown = shown_risk_flags if shown_risk_flags is not None else set()
    values: dict = {}
    payload = None
    started = time.time()
    for mode, chunk in graph.stream(graph_input, config, stream_mode=["custom", "updates", "values"]):
        elapsed = f"{time.time() - started:4.0f}s"
        if mode == "values":
            values = chunk
        elif mode == "custom":
            print(f"      · {chunk.get('node', '?')}: {chunk.get('message', chunk)}   ({elapsed.strip()})", flush=True)
        else:   # updates
            for node, update in chunk.items():
                if node == "__interrupt__":
                    payload = update[0].value          # a tuple of Interrupt objects
                    continue
                update = update or {}
                line = f"  ✔ {node:<20} {elapsed}"
                if update.get("status"):
                    line += f"   status={update['status']}"
                if node == "research":
                    line += f"   evidence={len(update.get('evidence', []))}"
                if node == "proposer":
                    line += f"   proposals={len(update.get('proposals', []))}"
                if node == "judge":
                    verdict = update.get("verdict", {})
                    line += f"   decision={verdict.get('decision')}   winner={verdict.get('winning_proposal_id')}"
                print(line, flush=True)
                new_flags = [f for f in update.get("risk_flags") or [] if f not in shown]
                if new_flags:                           # shown the moment a node records them
                    print_risk_flags({"risk_flags": new_flags})
                    shown.update(new_flags)
                for w in update.get("withdrawn_risk_flags") or []:
                    if ("withdrawn", w["flag"]) not in shown:
                        print(f"   ↩️  Risk flag withdrawn after your answers: {w['flag']}\n      reason: {w['reason']}")
                        shown.add(("withdrawn", w["flag"]))
                if node == "clarification" and update.get("project_name"):
                    print(f"   🧩 project now: {update['project_name']}")
    return values, payload


def print_risk_flags(state: dict) -> None:
    """Informational: risky aspects (payments, personal data, minors, scraping...) the agents must design for."""
    flags = state.get("risk_flags") or []
    if not flags:
        return
    print("\n⚠️  Risk flags noted (the proposals must address these):")
    for flag in flags:
        print(f"   - {flag}")


def print_case(state: dict) -> None:
    print(f"\n🧩 Project: {state.get('project_name')}  [{state.get('project_category')}]")
    print(f"   Summary:     {state.get('idea_summary')}")
    print(f"   Profile:     {state.get('project_profile')}")
    print(f"   Features:    {state.get('requested_features')}")
    print(f"   Constraints: {state.get('constraints')}")
    print(f"   Assumptions: {state.get('assumptions')}")
    print_risk_flags(state)
    for w in state.get("withdrawn_risk_flags") or []:
        print(f"   ↩️  Withdrawn: {w['flag']}  ({w['reason']})")


def print_research(state: dict) -> None:
    evidence = state.get("evidence", [])
    print(f"\n🔎 Queries ({len(state.get('research_queries', []))}):")
    for q in state.get("research_queries", []):
        print(f"   - {q}")

    print(f"\n📚 Evidence kept: {len(evidence)}")
    for d in DOMAINS:
        lane = [e for e in evidence if e["domain"] == d]
        print(f"\n  ── {DOMAIN_LABELS[d]} — {len(lane)} item(s)")
        for e in lane:
            quote = "quote" if e["is_direct_quote"] else "paraphrase"
            print(f"\n  {e['evidence_id']}  [{e['source_type']} | {e.get('evidence_strength', 'unknown')}]  "
                  f"relevance={e['relevance_score']:.2f}  ({quote})")
            print(f"     {e['source_title'][:90]}")
            print(f"     {e['source_url']}")
            print(f"     \"{e['relevant_excerpt'][:200]}\"")
            if e.get("claims_supported"):
                print(f"     claims: {e['claims_supported'][:2]}")
            if e.get("feedback_context"):
                c = e["feedback_context"]
                print(f"     feedback: {c.get('product', '?')} | {c.get('feedback_type')} | recurring={c.get('is_recurring')} | "
                      f"{c.get('experience_described', '')[:100]}")
            print(f"     notes: {e['reliability_notes'][:160]}")

    rejected = state.get("rejected_sources", [])
    print(f"\n🗑  Rejected sources: {len(rejected)}")
    for r in rejected:
        print(f"   - [{r.get('domain', '?'):<6}] {r['title'][:50]:<50}  → {r['reason'][:70]}")

    print("\n🕳  Evidence gaps:")
    for g in state.get("evidence_gaps", []) or ["(none)"]:
        print(f"   - {g}")

    print("\n⚔️  Conflicting claims:")
    for c in state.get("conflicting_claims", []) or [{"topic": "(none)", "evidence_ids": [], "description": ""}]:
        print(f"   - {c['topic']} {c['evidence_ids']} {c['description'][:120]}")

    print(f"\n📝 Research summary:\n{state.get('research_summary', '')}")


def _bullets(items: list, limit: int = 4, indent: str = "         ") -> str:
    shown = [f"{indent}• {i}" for i in items[:limit]]
    if len(items) > limit:
        shown.append(f"{indent}• … (+{len(items) - limit} more)")
    return "\n".join(shown) if shown else f"{indent}(none)"


def _print_proposal(proposal: dict, score: dict | None, criticism: dict | None, winner: bool) -> None:
    pid = proposal["proposal_id"]
    crown = "🏆 " if winner else "   "
    total = f"{score['weighted_total']:.2f}" if score and score.get("weighted_total") is not None else "n/a"
    print(f"\n  {crown}{pid}  {proposal['name']}   total={total}/10  confidence={(score or {}).get('confidence', '?')}  "
          f"difficulty={proposal['difficulty']}")
    print(f"      {proposal['summary'][:300]}")
    print(f"      problem:     {proposal['problem_addressed'][:200]}")
    print(f"      core features:\n{_bullets(proposal['core_features'])}")
    arch = proposal["architecture"]
    print(f"      architecture: fe={arch['frontend']} | be={arch['backend']} | db={arch['database']} | "
          f"ext={arch['external_services']} | ai={arch['ai_components']}")
    print(f"      technologies:\n{_bullets(proposal['technologies'])}")
    print(f"      beats alternatives: {proposal['how_it_beats_alternatives'][:200]}")
    print(f"      feasibility: {proposal['feasibility_notes'][:200]}")
    print(f"      evidence:    {proposal['supporting_evidence_ids']}")
    if score:
        crit = ", ".join(f"{c['criterion']}={c['score']:g}" for c in score["criterion_scores"])
        print(f"      scores:      {crit}")
    if criticism:
        print(f"      critic ({len(criticism['points'])} point(s)): {criticism['overall_assessment'][:200]}")
        for pt in criticism["points"][:3]:
            print(f"         - [{pt['severity']} | {pt['category']} | {pt['basis']}] {pt['issue'][:150]}")


def print_debate(state: dict) -> None:
    proposals = state.get("proposals", [])
    criticisms = {c["proposal_id"]: c for c in state.get("criticisms", [])}
    scores = {s["proposal_id"]: s for s in state.get("scores", [])}
    verdict = state.get("verdict", {})
    winner = verdict.get("winning_proposal_id")

    print(f"\n⚖️  Verdict: {verdict.get('decision')}   winner={winner}   (debate round {state.get('debate_round')}, "
          f"research retries {state.get('research_retry_count')})")
    print(f"   {verdict.get('reason', '').replace(chr(10), chr(10) + '   ')}")
    print(f"   domain status: {verdict.get('domain_status')}")
    if state.get("proposer_notes"):
        print(f"   proposer note: {state['proposer_notes']}")
    for proposal in sorted(proposals, key=lambda p: (scores.get(p["proposal_id"], {}).get("weighted_total") or 0), reverse=True):
        _print_proposal(proposal, scores.get(proposal["proposal_id"]), criticisms.get(proposal["proposal_id"]),
                        proposal["proposal_id"] == winner)
    if verdict.get("required_evidence"):
        print("\n📌 Required evidence (for a follow-up search):")
        for r in verdict["required_evidence"]:
            print(f"   - {r}")
    if verdict.get("material_contradictions"):
        print("\n⚡ Material contradictions:")
        for c in verdict["material_contradictions"]:
            print(f"   - {c}")
    if verdict.get("clarification_questions"):
        print("\n❓ Questions the Judge would like answered:")
        for q in verdict["clarification_questions"]:
            print(f"   - {q}")


def print_report(state: dict) -> None:
    r = state.get("final_report")
    if not r:
        print("\n(no final report)")
        return
    print("\n" + "═" * 100)
    print(f"📋 REPORT — {r['project_name']}   status={state.get('status')}   "
          f"{'CONDITIONAL' if r['is_conditional'] else 'confident'}")
    print("═" * 100)
    print_risk_flags(r)
    print(f"\n{r['overview']}\n")
    print(f"Method: {r['research_methodology']}")

    winner = r.get("winner")
    if winner:
        print(f"\n{'─' * 100}\n  🏆 Recommended solution")
        _print_proposal(winner["proposal"], winner.get("score"), None, True)
        print(f"     verification: {winner.get('verification_counts')}")
        for n in winner.get("verification_notes", [])[:4]:
            print(f"        - {n[:160]}")
        for o in winner.get("critic_key_objections", [])[:3]:
            print(f"     critic: {o[:160]}")
        print("     key evidence:")
        for e in winner.get("key_evidence", [])[:6]:
            print(f"        [{e['verification_status']}] {e['title'][:70]}  {e['url']}")
    else:
        print(f"\n  (no recommended solution) {r.get('no_winner_reason', '')[:300]}")
    for alt in r.get("alternatives", []):
        print(f"\n{'─' * 100}\n  Alternative")
        _print_proposal(alt["proposal"], alt.get("score"), None, False)

    def section(title, items):
        print(f"\n{title}")
        for x in items or ["(none)"]:
            print(f"   - {x}")

    section("✅ Why this solution:", r["why_this_solution"])
    section("❓ Uncertainties:", r["uncertainties"])
    section("⛔ Claims not supported by their evidence:", r["unsupported_claims"])
    section("🔍 Unresolved questions:", r["unresolved_questions"])
    section("➡️  Next steps before planning the build:", r["next_steps"])
    print(f"\nℹ️  {r['disclaimer']}")
    if state.get("metrics"):
        m = state["metrics"]
        print(f"\n⏱  active {m.get('active_seconds')}s · debate rounds {m.get('debate_rounds')} · research retries "
              f"{m.get('research_retries')} · evidence {m.get('evidence_count')} · claims checked {m.get('claims_checked')}")
