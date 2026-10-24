"""Run intake + the Research node on an idea and cache the state for later steps (no clarification round).

Run from the backend/ folder:
    uv run python scripts/run_research.py "A simple calculator web app"
Saves backend/.cache/research_state.json so later scripts can reuse the research without paying for it again.
"""

import json
import sys
from pathlib import Path

from ai_decision_arena.config import session_mode
from ai_decision_arena.nodes.intake import intake_node
from ai_decision_arena.nodes.research import research_node
from print_helpers import print_case, print_research

CACHE_FILE = Path(__file__).resolve().parent.parent / ".cache" / "research_state.json"

question = " ".join(sys.argv[1:]) or "A simple calculator web app"
with session_mode("full"):
    state = {"question": question, "user_context": "", "mode": "full"}
    state.update(intake_node(state))
    state["assumptions"] = ["No clarification round in this script: the agents work from the idea as written."]
    state.update(research_node(state))

print_case(state)
print_research(state)
CACHE_FILE.parent.mkdir(exist_ok=True)
CACHE_FILE.write_text(json.dumps(state, indent=2, default=str))
print(f"\n💾 State saved to {CACHE_FILE}")
