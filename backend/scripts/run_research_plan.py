"""Plan the search queries for an idea (one Claude call), run them on Tavily, show the hits per domain.

Run from the backend/ folder:
    uv run python scripts/run_research_plan.py "A simple calculator web app"
"""

import sys

from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.research.planner import plan_queries
from ai_decision_arena.research.search import run_searches
from ai_decision_arena.schemas import DOMAINS

question = " ".join(sys.argv[1:]) or "A simple calculator web app"
state = {"question": question, "user_context": "", "mode": "full"}
state.update(intake_node(state))
print("🧠 Planning queries with Claude...\n")
plan = plan_queries(state)
print(f"Search term: {plan.search_term}\n")
for i, q in enumerate(plan.queries, 1):
    extra = f"  prefer+={q.preferred_domains}" if q.preferred_domains else ""
    print(f"  Q{i} [{q.domain:<6} | {q.topic:<24}] {q.query}{extra}")

print("\n🔎 Searching with Tavily...\n")
hits, failures = run_searches(plan.queries)

for d in DOMAINS:
    lane = [h for h in hits if h.domain == d]
    print(f"── {d}: {len(lane)} hit(s)")
    for h in lane[:8]:
        print(f"   {h.tavily_score:.2f}  [{h.source_type:<20}] {h.title[:70]}\n         {h.url}")
for f in failures:
    print(f"❌ [{f.domain}] {f.query!r}: {f.error_type} {f.message[:100]}")
