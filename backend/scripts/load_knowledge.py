"""Fill the knowledge base, then try a search.

Run from the backend/ folder:
    uv run python scripts/load_knowledge.py                          # load + demo search
    uv run python scripts/load_knowledge.py "why is 0.1 + 0.2 wrong"  # load + your own search

1. Loads backend/knowledge/*.md (curated docs). Re-running updates them and deletes curated rows whose file is gone.
2. Copies the evidence of sessions saved before the knowledge base existed (new sessions add theirs at completion).
3. Runs one full-text search and prints the results with their citation ids.
"""

import sys

from ai_decision_arena.db.repository import backfill_knowledge_from_evidence
from ai_decision_arena.knowledge import load_curated, search

query = " ".join(sys.argv[1:]) or "how do I keep API keys out of the frontend"

loaded, deleted = load_curated()
print(f"curated docs loaded: {loaded} (old curated rows deleted: {deleted})")
print(f"evidence copied from earlier sessions: {backfill_knowledge_from_evidence()}")
print(f"\nsearch: {query!r}")
for r in search(query):
    print(f"- [{r['id']}] ({r['kind']}) {r['title'][:80]}\n    {r['url']}\n    {r['excerpt'][:160]}...")
