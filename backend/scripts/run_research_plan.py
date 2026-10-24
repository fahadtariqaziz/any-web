"""Step 4.1 — plan search queries with Claude (3 domains), run them on Tavily, show the hits.

Run from the backend/ folder:
    uv run python scripts/run_research_plan.py

Uses a saved, already-clarified demo state, so no questions are asked.
"""

from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from ai_decision_arena.schemas import DOMAINS
from demo_data import CLARIFIED_STATE

print("🧠 Planning queries with Claude...\n")
plan = plan_queries(CLARIFIED_STATE)
print(f"Search term: {plan.search_term}\n")
for i, q in enumerate(plan.queries, 1):
    domains = f"  prefer+={q.preferred_domains}" if q.preferred_domains else ""
    print(f"  Q{i} [{q.domain:<8} | {q.topic:<21}] {q.query}{domains}")

print("\n🔎 Searching with Tavily...\n")
hits, failures = run_searches(plan.queries)

for p in DOMAINS:
    lane = [h for h in hits if h.domain == p]
    print(f"── {p} domain: {len(lane)} hit(s)")
    for h in lane:
        print(f"  {h.tavily_score:.2f}  {h.source_type:<19} {h.title[:70]}")
        print(f"        {h.url}")
print(f"\n✅ {len(hits)} unique hits from {len(plan.queries)} queries")

if failures:
    print(f"⚠️  {len(failures)} failed queries (recorded as evidence gaps):")
    for f in failures:
        print(f"   - [{f.domain}] {f.query!r}: {f.error_type} (retryable={f.retryable})")
