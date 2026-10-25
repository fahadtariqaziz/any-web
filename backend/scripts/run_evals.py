"""Run the prompt eval cases (backend/evals/<prompt>/*.json; ai_decision_arena/evals.py explains the format).

    uv run python scripts/run_evals.py                    # offline: test fakes, free, seconds (request / prompt checks)
    uv run python scripts/run_evals.py --live             # real models: the cases marked "live" (cost printed)
    uv run python scripts/run_evals.py --prompt planner   # only one prompt's cases
Exit 1 when a case fails. Change a prompt → bump its version (prompts.py) → run its cases → lock (prompt_versions.py).
"""

import argparse
import importlib
import sys
from contextlib import contextmanager
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--live", action="store_true", help="real models (costs money); default: offline fakes")
parser.add_argument("--prompt", help="only the cases of this prompt id")
args = parser.parse_args()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not args.live:
    import tests.conftest as fakes          # noqa: F401  sets the test environment (fake keys, no DB) before the imports

from langgraph.graph import END, START, StateGraph  # noqa: E402

from ai_decision_arena import llm  # noqa: E402
from ai_decision_arena.evals import LLM_USERS, Request, load_cases, run_case  # noqa: E402
from ai_decision_arena.graph import NODES  # noqa: E402
from ai_decision_arena.prompts import REGISTRY  # noqa: E402
from ai_decision_arena.state import ArenaState  # noqa: E402

mode = "live" if args.live else "offline"
inner = llm.call_structured if args.live else fakes.FakeLLM()
if not args.live:
    import ai_decision_arena.nodes.planner as planner
    planner.resolve_model = lambda wanted: (wanted, "")


@contextmanager
def capture(requests: list[Request]):
    """Route every call_structured through a recorder (then the real or the fake function)."""
    def recorder(schema, system_prompt, user_content, **kwargs):
        requests.append(Request(schema.__name__, system_prompt, user_content))
        return inner(schema, system_prompt, user_content, **kwargs)
    modules = [importlib.import_module(m) for m in LLM_USERS]
    saved = [m.call_structured for m in modules]
    for m in modules:
        m.call_structured = recorder
    try:
        yield
    finally:
        for m, fn in zip(modules, saved):
            m.call_structured = fn


def node_runner(name: str | None):
    if not name:
        return None
    fn = NODES[name]

    def run(state: dict) -> dict:
        # a one-node graph, so get_config() / progress reporting work in the node exactly like in a real run
        captured: dict = {}

        def node(s):
            captured.update(fn(s) or {})
            return {}
        builder = StateGraph(ArenaState)
        builder.add_node(name, node)
        builder.add_edge(START, name)
        builder.add_edge(name, END)
        builder.compile().invoke(state, {"configurable": {"thread_id": "eval"}})
        return captured
    return run


cases = load_cases(args.prompt)
print(f"{len(cases)} case(s), mode {mode}\n")
results = []
for case in cases:
    unknown = case["prompt"] not in REGISTRY
    result = run_case(case, mode, node_runner(case.get("node")), capture)
    if unknown:
        result.failures.append(f"unknown prompt id {case['prompt']}")
        result.passed = False
    results.append(result)
    v = REGISTRY[case["prompt"]].version if not unknown else "?"
    status = "skip" if not result.ran else ("PASS" if result.passed else "FAIL")
    cost = f"  {result.calls} call(s) ${result.cost_usd:.4f}" if args.live and result.ran else ""
    print(f"{status:4}  {case['prompt']} v{v} / {case['id']}{cost}")
    for f in result.failures:
        print(f"        - {f}")
    if result.note and result.ran and not result.passed:
        print("        " + result.note.strip().replace("\n", "\n        ")[-1200:])

ran = [r for r in results if r.ran]
failed = [r for r in ran if not r.passed]
total = sum(r.cost_usd for r in ran)
print(f"\nEVALS ({mode}): {len(ran) - len(failed)}/{len(ran)} passed, {len(results) - len(ran)} skipped"
      + (f", cost ${total:.4f}" if args.live else ""))
sys.exit(1 if failed else 0)
