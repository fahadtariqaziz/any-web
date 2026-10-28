"""Live check of parallel tasks (implementer_parallel): two independent tasks built AT THE SAME TIME by real agents.

Like verify_m8: starts from backend/.cache/plan_calculator.json (an approved brief), replaces the plan with a tiny one
(T1 scaffold; T2 arithmetic and T3 formatting, both depending only on T1, separate files; Node's built-in test runner,
no package download), approves it like plan_review_router does, runs the real graph and stops before the build check.
Checks from facts: all tasks done (Python's verify commands), T2 and T3 ran in one step (parallel_with) and their agent
attempts overlapped in time (logs), the agents' denied calls, the re-run of every verify command now, ai-lab-2's git
status unchanged. Prints the time saved against running T2 and T3 one after another.
    uv run python -u scripts/verify_parallel.py          (≈ 1 minute, well under $1)
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from ai_decision_arena.config import REPO_ROOT, get_settings
from ai_decision_arena.graph import build_graph
from ai_decision_arena.plan import plan_hash, plan_is_approved, render_plan_markdown, tasks_from_plan
from ai_decision_arena.schemas import ImplementationPlan, PlanCommands, PlanPhase, PlanTask
from ai_decision_arena.workspace import sandbox
from ai_decision_arena.workspace.paths import workspace_for

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "plan_calculator.json"
failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True).stdout


PLAN = ImplementationPlan(
    summary="A calculator core: an arithmetic module and a number formatter, tested with node --test.",
    tech_stack=["ES modules (no build step)", "node:test (built into Node, no dependencies)"],
    project_structure=["src/calc.js: arithmetic", "src/format.js: display formatting", "tests/*.test.js: node:test",
                       "package.json: type module, test script"],
    dependencies=["none (Node built-ins only)"], architecture="Two independent modules.", data_model="none",
    api_endpoints=[], frontend_components=[], backend_services=[], integrations=[], ai_components="none",
    phases=[PlanPhase(id="P1", name="Setup", goal="The test runner works."),
            PlanPhase(id="P2", name="Modules", goal="Both modules work and are tested.")],
    tasks=[
        PlanTask(id="T1", phase="P1", title="Create the test setup",
                 description="Create package.json with \"type\": \"module\" and the script \"test\": \"node --test\", and "
                             "tests/smoke.test.js (node:test + node:assert) asserting 1 + 1 === 2.",
                 depends_on=[], files=["package.json", "tests/smoke.test.js"],
                 acceptance_criteria=["npm test passes"], verify_commands=["npm test"]),
        PlanTask(id="T2", phase="P2", title="Add the arithmetic module",
                 description="Create src/calc.js exporting add, subtract, multiply and divide (divide by zero throws an "
                             "Error 'Cannot divide by zero') and tests/calc.test.js covering each function and the error.",
                 depends_on=["T1"], files=["src/calc.js", "tests/calc.test.js"],
                 acceptance_criteria=["all four operations correct", "divide by zero throws"],
                 verify_commands=["node --test tests/calc.test.js", "npm test"]),
        PlanTask(id="T3", phase="P2", title="Add the number formatter",
                 description="Create src/format.js exporting formatNumber(n): at most 10 significant digits, no trailing "
                             "zeros after the decimal point, '-0' shown as '0', and tests/format.test.js covering these.",
                 depends_on=["T1"], files=["src/format.js", "tests/format.test.js"],
                 acceptance_criteria=["10 significant digits", "no trailing zeros", "no negative zero"],
                 verify_commands=["node --test tests/format.test.js", "npm test"]),
    ],
    feature_coverage=[], testing_strategy=["node:test unit tests per module"],
    commands=PlanCommands(install=[], test=["npm test"], build=[], dev="npx serve"),
    risks_and_decisions=["none"],
)

if not CACHE.exists():
    sys.exit(f"{CACHE} is missing: run scripts/verify_m6.py first.")
settings = get_settings()
cached = json.loads(CACHE.read_text())
git_before = git_status()
markdown = render_plan_markdown(PLAN, cached.get("project_name", ""), 0, "verify_parallel (tiny plan)")
values = {k: v for k, v in cached.items() if k not in ("implementation_log", "implementation_cost_usd", "workspace_dir",
                                                       "current_task_id", "error", "completed_at", "metrics")}
values |= {"implementation_plan": PLAN.model_dump(mode="json"), "plan_markdown": markdown,
           "implementation_tasks": tasks_from_plan(PLAN), "plan_review_route": "approved",
           "plan_approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "plan_approved_hash": plan_hash(markdown), "status": "reporting"}
print(f"implementer {settings.implementer_model} (effort {settings.implementer_effort}), "
      f"implementer_parallel={settings.implementer_parallel}")
check(plan_is_approved(values), "the tiny plan is approved (plan hash + brief hash)")

thread_id = f"verify-parallel-{int(time.time())}"
config = {"configurable": {"thread_id": thread_id}}
graph = build_graph(InMemorySaver())
graph.update_state(config, values, as_node="plan_review_router")
t0 = time.monotonic()
for chunk in graph.stream(None, config, stream_mode="custom", interrupt_before=["build_check"]):
    print(f"   {time.monotonic() - t0:5.1f}s", chunk.get("message") if isinstance(chunk, dict) else chunk)
wall = time.monotonic() - t0
state = dict(graph.get_state(config).values)

print("\n1. tasks")
tasks = {t["id"]: t for t in state.get("implementation_tasks", [])}
for t in tasks.values():
    r = t.get("result") or {}
    agent = r.get("agent") or {}
    check(t["status"] == "done", f"{t['id']} {t['status']} after {t['attempts']} attempt(s): verify "
          f"{[(v['command'], v['exit_code']) for v in r.get('verify', [])]}, {agent.get('turns')} turns, "
          f"${agent.get('cost_usd')}, {agent.get('seconds')}s, files {r.get('files_changed')}")
check((tasks["T2"].get("result") or {}).get("parallel_with") == ["T3"], "T2 and T3 ran in the same step")

print("\n2. timing (agent logs)")
ws = workspace_for(thread_id)
spans = {}
for tid in ("T2", "T3"):
    text = (ws.logs / f"{tid}.log").read_text()
    stamps = re.findall(r"^(\S+) --- attempt (?:start|end)", text, re.M)
    spans[tid] = (datetime.fromisoformat(stamps[0]), datetime.fromisoformat(stamps[-1]))
overlap = (min(spans["T2"][1], spans["T3"][1]) - max(spans["T2"][0], spans["T3"][0])).total_seconds()
serial = sum((b - a).total_seconds() for a, b in spans.values())
together = (max(b for _, b in spans.values()) - min(a for a, _ in spans.values())).total_seconds()
check(overlap > 0, f"the two attempts overlapped by {overlap:.0f}s: together {together:.0f}s instead of {serial:.0f}s "
                   f"one after another (saved {serial - together:.0f}s)")
denied = [line for p in ws.logs.glob("T*.log") for line in p.read_text().splitlines() if "DENIED" in line]
print(f"  denied agent calls: {denied or 'none'}")

print("\n3. independent re-check")
for t in PLAN.tasks:
    for command in t.verify_commands:
        r = sandbox.run(ws, command, label="verify_parallel-recheck")
        check(r.ok, f"re-run now: {command} → {r.summary()}")
check(git_status() == git_before, "ai-lab-2's own git status is unchanged")
print(f"\nimplementer phase {wall:.0f}s, cost ${state.get('implementation_cost_usd')}; workspace kept: {ws.root}")
print(f"PARALLEL VERIFY: {'PASS' if not failures else 'FAIL'}")
sys.exit(0 if not failures else 1)
