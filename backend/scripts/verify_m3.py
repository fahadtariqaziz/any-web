"""M3 live check: the debate (proposer → critic → judge → evidence checker → report) on real research for the
standard test idea, a simple calculator web app.

Reuses backend/.cache/research_calculator.json when present (written on the first run), so repeated runs only pay
for the debate: 1 proposer call, 2-3 critic calls, 1 judge call, 1 checker call, 1 report call.
    uv run python scripts/verify_m3.py            # reuse cached research if available
    uv run python scripts/verify_m3.py --fresh    # run intake + research again (Tavily + 4 Claude calls)
Also writes backend/.cache/debate_calculator.json (the full state) for the M4 verify.
"""

import json
import sys
from pathlib import Path

from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.final_report import final_report_node
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.judge import judge_node, weighted_total
from ai_decision_arena.nodes.proposer import proposer_node
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.schemas import DOMAINS, ProposalScore

IDEA = "A simple calculator web app"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
RESEARCH_CACHE = CACHE_DIR / "research_calculator.json"
DEBATE_CACHE = CACHE_DIR / "debate_calculator.json"
DECISIONS = {"proceed", "request_more_research", "request_clarification", "insufficient_evidence"}

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


settings = get_settings()
print(f"model: {settings.anthropic_model}")
if RESEARCH_CACHE.exists() and "--fresh" not in sys.argv:
    state = json.loads(RESEARCH_CACHE.read_text())
    print(f"research: reused {RESEARCH_CACHE} ({len(state['evidence'])} evidence records)")
else:
    state = {"question": IDEA, "user_context": "", "mode": "full"}
    state.update(intake_node(state))
    state["assumptions"] = ["Basic arithmetic only, runs in the browser, no accounts (assumed for this check)."]
    state.update(research_node(state))
    CACHE_DIR.mkdir(exist_ok=True)
    RESEARCH_CACHE.write_text(json.dumps(state, indent=2, default=str))
    print(f"research: ran live, {len(state['evidence'])} evidence records, cached to {RESEARCH_CACHE}")
known_ids = {e["evidence_id"] for e in state["evidence"]}

# --- proposer ---
state.update(proposer_node(state))
proposals = state["proposals"]
print(f"\n=== proposer: {len(proposals)} proposal(s), status {state['proposer_status']}")
for p in proposals:
    print(f"  {p['proposal_id']}  {p['name']}  [{p['difficulty']}]  cites {p['supporting_evidence_ids']}")
    print(f"     fe={p['architecture']['frontend']} | be={p['architecture']['backend']} | db={p['architecture']['database']}")
    print(f"     MVP: {p['core_features'][:4]}")
check(2 <= len(proposals) <= 3, f"2-3 proposals ({len(proposals)})")
check([p["proposal_id"] for p in proposals] == [f"proposal_{c}" for c in "abc"[:len(proposals)]], "ids are proposal_a, proposal_b, ...")
check(all(set(p["supporting_evidence_ids"]) <= known_ids for p in proposals), "every cited evidence id exists")
check(all(p["supporting_evidence_ids"] for p in proposals), "every proposal cites evidence")
check(all(p["core_features"] and p["user_journey"] and p["technologies"] for p in proposals), "every proposal has features, journey, technologies")
check(len({p["name"] for p in proposals}) == len(proposals), "proposal names differ")

# --- critic ---
state.update(critic_node(state))
print(f"\n=== critic: {[(c['proposal_id'], len(c['points'])) for c in state['criticisms']]}")
for c in state["criticisms"]:
    for pt in c["points"][:2]:
        print(f"  {c['proposal_id']} [{pt['severity']}/{pt['category']}/{pt['basis']}] {pt['issue'][:110]}")
check([c["proposal_id"] for c in state["criticisms"]] == [p["proposal_id"] for p in proposals], "one criticism per proposal, same order")
check(all(set(pt["evidence_ids"]) <= known_ids for c in state["criticisms"] for pt in c["points"]), "critic cites only real evidence")
check(all(pt["basis"] == "engineering_judgement" or pt["evidence_ids"] for c in state["criticisms"] for pt in c["points"]),
      "basis=evidence only with evidence ids")

# --- judge ---
state.update(judge_node(state))
verdict = state["verdict"]
print(f"\n=== judge: decision {verdict['decision']}, winner {verdict['winning_proposal_id']}")
for s in sorted(state["scores"], key=lambda s: s["weighted_total"], reverse=True):
    print(f"  {s['proposal_id']} total={s['weighted_total']}  confidence={s['confidence']}  "
          + ", ".join(f"{c['criterion'][:12]}={c['score']:g}" for c in s["criterion_scores"]))
print(f"  domain status: {verdict['domain_status']}")
if verdict["material_contradictions"]:
    print(f"  contradictions: {verdict['material_contradictions']}")
if verdict["clarification_questions"]:
    print(f"  questions: {verdict['clarification_questions']}")
print(f"  reason: {verdict['reason'][:400]}")
check(verdict["decision"] in DECISIONS, f"decision is valid ({verdict['decision']})")
check([s["proposal_id"] for s in state["scores"]] and set(s["proposal_id"] for s in state["scores"]) <= {p["proposal_id"] for p in proposals},
      "scores refer to real proposals")
check(all(s["weighted_total"] == weighted_total(ProposalScore.model_validate(s), settings.rubric_weights) for s in state["scores"]),
      "weighted totals computed by Python")
best = max(state["scores"], key=lambda s: s["weighted_total"])["proposal_id"] if state["scores"] else None
check(verdict["winning_proposal_id"] == best, "winner has the highest weighted total")
check(set(verdict["domain_status"]) == set(DOMAINS), "domain status covers all three domains")

# --- the winner's claim check (consolidated by the judge since 2026-10-29) + report ---
cv = state["checker_verdict"]
print(f"\n=== checker: {cv['claims_checked']} claims, decision {cv['decision']}, gaps {cv['material_gaps']}")
for r in state["verification_results"][:6]:
    print(f"  [{r['status']}] {r['claim'][:100]}")
check(all(r["proposal_id"] == verdict["winning_proposal_id"] for r in state["verification_results"]), "checker verified the winner only")
check(cv["decision"] in ("proceed", "request_more_research"), "checker decision valid")

state.update(final_report_node(state))
r = state["final_report"]
print(f"\n=== report: winner {r['winner']['proposal']['proposal_id'] if r['winner'] else None}, "
      f"{len(r['alternatives'])} alternative(s), conditional={r['is_conditional']}")
print(f"  overview: {r['overview'][:300]}")
print(f"  why: {r['why_this_solution'][:3]}")
print(f"  next steps: {r['next_steps'][:3]}")
check(bool(r["overview"]) and bool(r["next_steps"]), "report has an overview and next steps")
check((r["winner"] or {}).get("proposal", {}).get("proposal_id") == verdict["winning_proposal_id"], "report winner matches the verdict")
check(len(r["alternatives"]) == len(proposals) - (1 if r["winner"] else 0), "report lists the other proposals as alternatives")

CACHE_DIR.mkdir(exist_ok=True)
DEBATE_CACHE.write_text(json.dumps(state, indent=2, default=str))
print(f"\n💾 full state saved to {DEBATE_CACHE}")
print("\nM3 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
