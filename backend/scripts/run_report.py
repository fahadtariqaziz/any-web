"""Phase 6 — run evidence checker → final report → completion on cached debate results.

Run from the backend/ folder:
    uv run python scripts/run_debate.py      # once, creates backend/.cache/debate_state.json
    uv run python scripts/run_report.py

How it skips research: the cached state is injected into a fresh thread "as if the judge had just run"
(graph.update_state(..., as_node="judge")), then the graph continues from the judge's outgoing edge.
If the evidence checker asks for more research, those nodes really run.
"""

import json
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.graph import build_graph
from print_helpers import print_report, stream_graph

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
DEBATE_FILE = CACHE_DIR / "debate_state.json"
if not DEBATE_FILE.exists():
    sys.exit(f"❌ {DEBATE_FILE} not found. Run `uv run python scripts/run_debate.py` first.")
state = json.loads(DEBATE_FILE.read_text())
if state.get("verdict", {}).get("decision") != "proceed":
    print(f"ℹ️  Cached verdict was {state['verdict']['decision']!r}; forcing 'proceed' so the checker runs on the cached winners.")
    state["verdict"]["decision"] = "proceed"
state.setdefault("started_at", "cached")

graph = build_graph(checkpointer=InMemorySaver())
thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}, "run_name": "report_demo", "metadata": {"thread_id": thread_id, "step": "6.3"}}
graph.update_state(config, state, as_node="judge")       # pretend the judge just produced this state
print(f"📂 Loaded {len(state.get('care_plans', []))} plans / {len(state.get('evidence', []))} evidence from cache; thread {thread_id}")

result, payload = stream_graph(graph, None, config)      # None = continue the thread
while payload is not None:
    if payload.get("error"):                              # clarification pause (only if the judge sent us there)
        print(f"⚠️  {payload['error']}")
    reply = {"answers": {q: input(f"Q: {q}\n> ") for q in payload.get("questions", [])}}
    result, payload = stream_graph(graph, Command(resume=reply), config)

print(f"\n✅ Finished with status: {result['status']}")
if result["status"] == "failed":
    err = result.get("error") or {}
    sys.exit(f"❌ {err.get('category')} in {err.get('node')}: {err.get('message')}")
print_report(result)
(CACHE_DIR / "final_report.json").write_text(json.dumps(result.get("final_report"), indent=2, default=str))
print(f"\n💾 Report saved to {CACHE_DIR / 'final_report.json'}")
