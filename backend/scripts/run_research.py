"""Step 4.2 — run ONLY the Research node on a saved, already-clarified state (no questions).

Run from the backend/ folder:
    uv run python scripts/run_research.py

Saves the resulting state to backend/.cache/research_state.json so run_debate.py can
reuse it without paying for research again.
"""

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.research import research_node
from ai_decision_arena.state import ArenaState
from demo_data import CLARIFIED_STATE
from print_helpers import print_research, stream_graph

CACHE_FILE = Path(__file__).resolve().parent.parent / ".cache" / "research_state.json"

builder = StateGraph(ArenaState)
builder.add_node("research", research_node)
builder.add_edge(START, "research")
builder.add_edge("research", END)
graph = builder.compile()

print("🔎 Researching 3 lanes (planner → Tavily → 3 evidence extractors). Usually takes about 1 minute...")
result, _ = stream_graph(graph, CLARIFIED_STATE, {"run_name": "research_demo", "metadata": {"step": "4.2"}})
print_research(result)

CACHE_FILE.parent.mkdir(exist_ok=True)
CACHE_FILE.write_text(json.dumps(result, indent=2, default=str))
print(f"\n💾 Saved state to {CACHE_FILE} (used by run_debate.py)")
