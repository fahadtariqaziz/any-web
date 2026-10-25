"""M2 live check: one real research pass (Tavily + Claude) for the standard test idea, a simple calculator web app.

Run from the backend/ folder (1 intake call, 1 planner call, up to 9 Tavily searches, 3 extractor calls):
    uv run python scripts/verify_m2.py
Checks that every evidence record points at a URL Tavily actually returned, that all three domains were searched,
and that the summaries exist. Prints what was found, then PASS or FAIL.
"""

import sys
from typing import get_args

from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes import research as research_module
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.research.sources import normalize_url
from ai_decision_arena.schemas import DOMAINS, EvidenceStrength, SourceType

IDEA = "A simple calculator web app"
HEALTH_WORDS = ("symptom", "diagnos", "medication", "patient", "clinical")

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


# Record every hit Tavily returned, so we can prove the evidence URLs were not invented.
seen_hits: dict[str, object] = {}
original_run_searches = research_module.run_searches


def recording_run_searches(queries):
    hits, search_failures = original_run_searches(queries)
    for h in hits:
        seen_hits[normalize_url(h.url)] = h
    return hits, search_failures


research_module.run_searches = recording_run_searches

settings = get_settings()
print(f"model: {settings.anthropic_model}  queries per domain: {settings.queries_per_domain}  "
      f"hits per domain: {settings.max_hits_per_domain}")
state = {"question": IDEA, "user_context": "", "mode": "full"}
state.update(intake_node(state))
state["assumptions"] = ["Basic arithmetic only, runs in the browser, no accounts (assumed for this check)."]
print(f"\n=== {IDEA}  →  project_name: {state['project_name']}")
out = research_node(state)

queries = out["research_queries"]
evidence = out["evidence"]
print("\nqueries:")
for q in queries:
    print("   ", q)
print(f"\nhits returned by Tavily: {len(seen_hits)}   evidence kept: {len(evidence)}   rejected: {len(out['rejected_sources'])}")
for d in DOMAINS:
    kept = [e for e in evidence if e["domain"] == d]
    print(f"  [{d}] {len(kept)} evidence; summary: {'yes' if d in out['domain_summaries'] else 'no'}")
    for e in kept[:2]:
        print(f"      {e['evidence_id']} {e['source_type']:<20} {e['source_title'][:70]}")
if out["evidence_gaps"]:
    print("gaps:", out["evidence_gaps"])

check(all(any(q.startswith(f"[{d}]") for q in queries) for d in DOMAINS), "every domain was searched")
check(len(evidence) > 0, "at least one evidence record")
check([e["evidence_id"] for e in evidence] == [f"ev_{i:03d}" for i in range(1, len(evidence) + 1)], "evidence ids are sequential")
check(all(normalize_url(e["source_url"]) in seen_hits for e in evidence), "every evidence URL came from a Tavily hit")
check(all(e["domain"] in DOMAINS for e in evidence), "every evidence record has a valid domain")
check(all(e["source_type"] in get_args(SourceType) for e in evidence), "every source_type is in the vocabulary")
check(all(e["evidence_strength"] in get_args(EvidenceStrength) for e in evidence), "every evidence_strength is in the vocabulary")
check(all(e["feedback_context"] is None or e["domain"] == "apps" or e["source_type"] in ("review_site", "app_store", "community_discussion")
          for e in evidence), "feedback context only on review / store / community sources")
covered = {e["domain"] for e in evidence}
check(all(d in out["domain_summaries"] for d in covered), "every domain with evidence has a summary")
check(not any(w in out["research_summary"].lower() for w in HEALTH_WORDS), "no health vocabulary in the summaries")
check(out["status"] == "debating" and out["research_focus"] == [], "node leaves the state ready for the debate")

print("\nM2 VERIFY:", "PASS" if not failures else f"FAIL ({len(failures)} check(s) failed)")
sys.exit(0 if not failures else 1)
