"""Phase 5 — run ONLY the debate (proposer → critic → judge) on saved research results.

Run from the backend/ folder:
    uv run python scripts/run_research.py     # once, to create backend/.cache/research_state.json
    uv run python scripts/run_debate.py

Saves the resulting state to backend/.cache/debate_state.json (for Phase 6 scripts).
"""

import json
import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from ai_decision_arena.nodes.critic import critic_node
from ai_decision_arena.nodes.judge import judge_node
from ai_decision_arena.nodes.proposer import proposer_node
from ai_decision_arena.state import ArenaState
from print_helpers import print_debate, stream_graph

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
RESEARCH_FILE = CACHE_DIR / "research_state.json"
DEBATE_FILE = CACHE_DIR / "debate_state.json"

if not RESEARCH_FILE.exists():
    sys.exit(f"❌ {RESEARCH_FILE} not found. Run `uv run python scripts/run_research.py` first.")
state = json.loads(RESEARCH_FILE.read_text())
print(f"📂 Loaded {len(state.get('evidence', []))} evidence items from {RESEARCH_FILE.name}")

builder = StateGraph(ArenaState)
builder.add_node("proposer", proposer_node)
builder.add_node("critic", critic_node)
builder.add_node("judge", judge_node)
builder.add_edge(START, "proposer")
builder.add_edge("proposer", "critic")
builder.add_edge("critic", "judge")
builder.add_edge("judge", END)
graph = builder.compile()

print("⚔️  Debating (3 proposers → 3 critics → 3 judges, each lane in parallel). Usually takes 2-3 minutes...")
result, _ = stream_graph(graph, state, {"run_name": "debate_demo", "metadata": {"step": "5.3"}})
print_debate(result)

DEBATE_FILE.write_text(json.dumps(result, indent=2, default=str))
print(f"\n💾 Saved state to {DEBATE_FILE}")
