"""Write the eval fixtures (backend/evals/fixtures/*.json): real states of ONE fake-pipeline run (test fakes, no
network, no cost), taken just before the node an eval case runs.

    uv run python scripts/make_eval_fixtures.py

Fixtures:
- built_calculator:      a built app at the change pause, after change request C1 ("Add a percent key...") was done;
- replan_brief_writer:   the same app right before brief_writer for "Plan a bigger change" (scientific mode);
- replan_planner:        right after the user approved that updated brief, before the planner's extension.
Re-run after a state / schema change that the cases depend on; the files are committed (deterministic fake content,
except timestamps and the tmp workspace path).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests.conftest as fakes  # noqa: E402  (sets the test environment first: fake keys, no DB, tmp projects dir)

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from ai_decision_arena.evals import FIXTURES_DIR, LLM_USERS  # noqa: E402
from ai_decision_arena.graph import build_graph  # noqa: E402
from ai_decision_arena.nodes import implementer, planner, research  # noqa: E402
from ai_decision_arena.workspace.processes import MemoryRuntimeStore, ProcessManager, set_manager  # noqa: E402

PERCENT = "Add a percent key (%): 430 - 20% = 344 and 430 + 20% = 516."
SCIENTIFIC = "Make it a scientific calculator as well: sin, cos, tan, log, ln, square root, powers."

llm = fakes.FakeLLM()
for module in LLM_USERS:
    setattr(sys.modules.get(module) or __import__(module, fromlist=["x"]), "call_structured", llm)
planner.resolve_model = implementer.resolve_model = lambda wanted: (wanted, "")
implementer.run_agent_task = fakes.FakeAgent()
research.run_searches = fakes.fake_run_searches
manager = ProcessManager(store=MemoryRuntimeStore())
set_manager(manager)

graph = build_graph(InMemorySaver())
config = {"configurable": {"thread_id": "eval-calculator"}}
graph.invoke({"question": "A simple calculator web app", "user_context": "", "mode": "full"}, config)


def pause() -> str:
    snap = graph.get_state(config)
    return snap.interrupts[0].value["type"] if snap.next else "finished"


def answer(body: dict) -> None:
    graph.invoke(Command(resume=body), config)


for _ in range(10):
    kind = pause()
    if kind == "change_request":
        break
    answer({"answers": {q: "Keep it simple: a browser calculator for everyone." for q in
                        graph.get_state(config).interrupts[0].value["questions"]}} if kind == "clarification"
           else {"action": "approve"})
answer({"action": "change", "request": PERCENT})
assert pause() == "change_request", pause()
fixtures = {"built_calculator": dict(graph.get_state(config).values)}

answer({"action": "replan", "request": SCIENTIFIC})
assert pause() == "brief_review", pause()
for snap in graph.get_state_history(config):                 # newest first: the checkpoint before brief_writer
    if snap.next == ("brief_writer",):
        fixtures["replan_brief_writer"] = dict(snap.values)
        break
answer({"action": "approve"})
for snap in graph.get_state_history(config):
    if snap.next == ("planner",):
        fixtures["replan_planner"] = dict(snap.values)
        break
manager.stop_all()

FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
for name, state in fixtures.items():
    path = FIXTURES_DIR / f"{name}.json"
    path.write_text(json.dumps(state, indent=1, sort_keys=True, default=str) + "\n")
    print(f"{path.relative_to(FIXTURES_DIR.parents[1])}: {len(json.dumps(state, default=str)) // 1024} kB, "
          f"current_node {state.get('current_node')}, tasks {[t['id'] for t in state.get('implementation_tasks', [])]}")
