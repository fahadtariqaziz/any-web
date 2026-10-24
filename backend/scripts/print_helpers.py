"""Shared terminal printing for the demo scripts, incl. live streaming of graph progress."""

import time

from ai_decision_arena.schemas import PERSPECTIVE_LABELS, PERSPECTIVES


def stream_graph(graph, graph_input, config, shown_red_flags: set | None = None) -> tuple[dict, dict | None]:
    """Run the graph while printing what is happening:
    - "custom" events = progress lines emitted by nodes while they run (progress.report),
    - "updates"       = one line per finished node, red flags the moment they are recorded,
    - "values"        = the full state after each step; the last one is returned.
    Returns (final_state_values, interrupt_payload_or_None)."""
    shown = shown_red_flags if shown_red_flags is not None else set()
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
                if node == "judge":
                    verdict = update.get("verdict", {})
                    line += f"   decision={verdict.get('decision')}   winners={verdict.get('winning_plan_ids')}"
                print(line, flush=True)
                new_flags = [f for f in update.get("risk_flags") or [] if f not in shown]
                if new_flags:                           # shown the moment a node records them
                    print_red_flags({"risk_flags": new_flags})
                    shown.update(new_flags)
                for w in update.get("withdrawn_risk_flags") or []:
                    if ("withdrawn", w["flag"]) not in shown:
                        print(f"   ↩️  Red flag withdrawn after your answers: {w['flag']}\n      reason: {w['reason']}")
                        shown.add(("withdrawn", w["flag"]))
                if node == "clarification" and update.get("project_name"):
                    print(f"   🩺 condition now: {update['project_name']}")
    return values, payload


def print_red_flags(state: dict) -> None:
    """Shown FIRST whenever intake or clarification recorded a possible emergency."""
    flags = state.get("risk_flags") or []
    if not flags:
        return
    print("\n" + "!" * 100)
    print("🚨 POSSIBLE EMERGENCY SIGNS WERE REPORTED. This tool gives information only, not medical care.")
    for flag in flags:
        print(f"   - {flag}")
    print("   If any of these is happening now, contact emergency services or go to the nearest emergency department.")
    print("!" * 100)


def print_case(state: dict) -> None:
    print(f"\n🧩 Project: {state.get('project_name')}  [{state.get('project_category')}]")
    print(f"   Summary:     {state.get('idea_summary')}")
    print(f"   Profile:     {state.get('project_profile')}")
    print(f"   Symptoms:    {state.get('symptoms')}")
    print(f"   Constraints: {state.get('constraints')}")
    print(f"   Assumptions: {state.get('assumptions')}")
    if state.get("risk_flags"):
        print(f"   🚨 Red flags: {state['risk_flags']}  → seek medical care promptly")
    for w in state.get("withdrawn_risk_flags") or []:
        print(f"   ↩️  Withdrawn: {w['flag']}  ({w['reason']})")


def print_research(state: dict) -> None:
    evidence = state.get("evidence", [])
    print(f"\n🔎 Queries ({len(state.get('research_queries', []))}):")
    for q in state.get("research_queries", []):
        print(f"   - {q}")

    print(f"\n📚 Evidence kept: {len(evidence)}")
    for p in PERSPECTIVES:
        lane = [e for e in evidence if e["perspective"] == p]
        print(f"\n  ── {PERSPECTIVE_LABELS[p]} — {len(lane)} item(s)")
        for e in lane:
            quote = "quote" if e["is_direct_quote"] else "paraphrase"
            print(f"\n  {e['evidence_id']}  [{e['source_type']} | {e.get('evidence_strength', 'unknown')}]  "
                  f"relevance={e['relevance_score']:.2f}  ({quote})")
            print(f"     {e['source_title'][:90]}")
            print(f"     {e['source_url']}")
            print(f"     \"{e['relevant_excerpt'][:200]}\"")
            if e.get("claims_supported"):
                print(f"     claims: {e['claims_supported'][:2]}")
            if e.get("patient_context"):
                c = e["patient_context"]
                print(f"     patient: recurring={c['is_recurring']} | {c['experience_described'][:100]}")
            print(f"     notes: {e['reliability_notes'][:160]}")

    rejected = state.get("rejected_sources", [])
    print(f"\n🗑  Rejected sources: {len(rejected)}")
    for r in rejected:
        print(f"   - [{r.get('perspective', '?'):<8}] {r['title'][:50]:<50}  → {r['reason'][:70]}")

    print("\n🕳  Evidence gaps:")
    for g in state.get("evidence_gaps", []) or ["(none)"]:
        print(f"   - {g}")

    print("\n⚔️  Conflicting claims:")
    for c in state.get("conflicting_claims", []) or [{"topic": "(none)", "evidence_ids": [], "description": ""}]:
        print(f"   - {c['topic']} {c['evidence_ids']} {c['description'][:120]}")

    print(f"\n📝 Research summary:\n{state.get('research_summary', '')}")


def _bullets(items: list, limit: int = 3, indent: str = "         ") -> str:
    shown = [f"{indent}• {i}" for i in items[:limit]]
    if len(items) > limit:
        shown.append(f"{indent}• … (+{len(items) - limit} more)")
    return "\n".join(shown) if shown else f"{indent}(none)"


def print_debate(state: dict) -> None:
    plans = state.get("care_plans", [])
    criticisms = {c["plan_id"]: c for c in state.get("criticisms", [])}
    scores = {s["plan_id"]: s for s in state.get("scores", [])}
    verdict = state.get("verdict", {})
    winners = verdict.get("winning_plan_ids", {})

    print(f"\n⚖️  Verdict: {verdict.get('decision')}   (debate round {state.get('debate_round')}, "
          f"research retries {state.get('research_retry_count')})")
    print(f"   {verdict.get('reason', '').replace(chr(10), chr(10) + '   ')}")

    for p in PERSPECTIVES:
        lane = sorted((x for x in plans if x["perspective"] == p),
                      key=lambda x: (scores.get(x["plan_id"], {}).get("weighted_total") or 0), reverse=True)
        print(f"\n{'═' * 100}\n  {PERSPECTIVE_LABELS[p]}   status={verdict.get('perspective_status', {}).get(p)}")
        if state.get("proposer_notes", {}).get(p):
            print(f"  note: {state['proposer_notes'][p]}")
        for plan in lane:
            pid = plan["plan_id"]
            s = scores.get(pid, {})
            crown = "🏆 " if winners.get(p) == pid else "   "
            total = f"{s['weighted_total']:.2f}" if s.get("weighted_total") is not None else "n/a"
            print(f"\n  {crown}{pid}  {plan['name']}   total={total}/10  confidence={s.get('confidence', '?')}  "
                  f"difficulty={plan['difficulty']}")
            print(f"      {plan['summary'][:300]}")
            print(f"      routine:\n{_bullets(plan['daily_routine'])}")
            print(f"      diet:\n{_bullets(plan['diet'])}")
            print(f"      medications/treatments:\n{_bullets(plan['medications_treatments'])}")
            print(f"      timeline:   {plan['expected_timeline'][:200]}")
            print(f"      prevalence: {plan['prevalence_and_outlook'][:200]}")
            print(f"      safety:     {plan['safety_notes'][:200]}")
            print(f"      evidence:   {plan['supporting_evidence_ids']}")
            if s:
                crit = ", ".join(f"{c['criterion']}={c['score']:g}" for c in s["criterion_scores"])
                print(f"      scores:     {crit}")
            c = criticisms.get(pid)
            if c:
                print(f"      critic ({len(c['points'])} point(s)): {c['overall_assessment'][:200]}")
                for pt in c["points"][:2]:
                    print(f"         - [{pt['severity']} | {pt['category']} | {pt['basis']}] {pt['issue'][:150]}")

    if verdict.get("required_evidence"):
        print("\n📌 Required evidence (for a follow-up search):")
        for r in verdict["required_evidence"]:
            print(f"   - {r}")
    if verdict.get("clarification_questions"):
        print("\n❓ Questions the Judge would like answered:")
        for q in verdict["clarification_questions"]:
            print(f"   - {q}")


# --- Phase 6: final report -------------------------------------------------------------------

def print_report(state: dict) -> None:
    r = state.get("final_report")
    if not r:
        print("\n(no final report)")
        return
    print("\n" + "═" * 100)
    print(f"📋 FINAL REPORT — {r['project_name']}   status={state.get('status')}   "
          f"{'CONDITIONAL' if r['is_conditional'] else 'confident'}")
    print("═" * 100)
    if r.get("risk_flags"):
        print("🚨 Red flags:")
        for f in r["risk_flags"]:
            print(f"   - {f}")
    if r.get("withdrawn_risk_flags"):
        print("↩️  Withdrawn after your answers (shown for the record):")
        for f in r["withdrawn_risk_flags"]:
            print(f"   - {f}")
    print(f"\n{r['overview']}\n")
    print(f"Method: {r['research_methodology']}")

    for item in r["perspectives"]:
        print(f"\n{'─' * 100}\n  {PERSPECTIVE_LABELS[item['perspective']]}")
        plan = item.get("plan")
        if not plan:
            print(f"  (no plan) {item.get('unavailable_reason', '')[:300]}")
            continue
        score = item.get("score") or {}
        total = score.get("weighted_total")
        print(f"  🏆 {plan['name']}   total={total if total is None else f'{total:.2f}'}/10  confidence={score.get('confidence')}  "
              f"difficulty={plan['difficulty']}")
        print(f"     {plan['summary'][:400]}")
        print(f"     routine:\n{_bullets(plan['daily_routine'])}")
        print(f"     diet:\n{_bullets(plan['diet'])}")
        print(f"     medications/treatments:\n{_bullets(plan['medications_treatments'])}")
        print(f"     timeline:   {plan['expected_timeline'][:250]}")
        print(f"     prevalence: {plan['prevalence_and_outlook'][:250]}")
        print(f"     safety:     {plan['safety_notes'][:250]}")
        print(f"     verification: {item.get('verification_counts')}")
        for n in item.get("verification_notes", [])[:4]:
            print(f"        - {n[:160]}")
        for o in item.get("critic_key_objections", [])[:2]:
            print(f"     critic: {o[:160]}")
        print("     key evidence:")
        for e in item.get("key_evidence", [])[:5]:
            print(f"        [{e['verification_status']}] {e['title'][:70]}  {e['url']}")

    def section(title, items):
        print(f"\n{title}")
        for x in items or ["(none)"]:
            print(f"   - {x}")

    section("🤝 Where the perspectives agree:", r["where_perspectives_agree"])
    section("↔️  Where they differ:", r["where_perspectives_differ"])
    section("❓ Uncertainties:", r["uncertainties"])
    section("⛔ Claims not supported by their evidence:", r["unsupported_claims"])
    section("🔍 Unresolved questions:", r["unresolved_questions"])
    section("➡️  Next steps:", r["next_steps"])
    print(f"\nℹ️  {r['disclaimer']}")
    if state.get("metrics"):
        m = state["metrics"]
        print(f"\n⏱  active {m.get('active_seconds')}s · debate rounds {m.get('debate_rounds')} · research retries "
              f"{m.get('research_retries')} · evidence {m.get('evidence_count')} · claims checked {m.get('claims_checked')} "
              f"· errors {m.get('errors')}")
