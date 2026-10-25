"""M8 live check: the implementer builds a trivial approved plan end to end with the real coding agent.

Starts from backend/.cache/plan_calculator.json (written by verify_m6.py: an approved brief + plan), replaces the plan
with a TRIVIAL one (a static calculator page + tests on Node's built-in test runner, so no package download), approves
it exactly like plan_review_router does (hash), then runs the real graph from there: implementer (Claude Agent SDK on
the implementer model) task by task, Python verify commands, completion. Afterwards it checks, independently of what
the graph recorded:
- both tasks are "done" and their verify commands pass when re-run now;
- the files exist in generated_projects/<thread>/app; ai-lab-2's own `git status` did not change;
- no file in app/ contains the API key; the agent's file calls stayed inside app/ (hook log); cost is reported.
    uv run python -u scripts/verify_m8.py            (a few minutes, well under $1)
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from ai_decision_arena.config import REPO_ROOT, get_settings, session_mode
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


TRIVIAL_PLAN = ImplementationPlan(
    summary="A one-page calculator: a static HTML page plus a small arithmetic module, tested with node --test.",
    tech_stack=["Plain HTML + ES modules (no build step)", "node:test (built into Node, no dependencies)"],
    project_structure=["index.html: the page", "src/calc.js: add, subtract, multiply, divide",
                       "tests/page.test.js, tests/calc.test.js: node:test suites", "package.json: type module, test script"],
    dependencies=["none (Node built-ins only)"],
    architecture="A static page imports src/calc.js; no server code.",
    data_model="none", api_endpoints=[], frontend_components=["index.html: display + keypad"], backend_services=[],
    integrations=[], ai_components="none",
    phases=[PlanPhase(id="P1", name="Page", goal="A static page exists and is tested."),
            PlanPhase(id="P2", name="Arithmetic", goal="The arithmetic module works and is tested.")],
    tasks=[
        PlanTask(id="T1", phase="P1", title="Create the static page and the test setup",
                 description="Create package.json with \"type\": \"module\" and the script \"test\": \"node --test\". Create "
                             "index.html with the title 'Simple Calculator', an element with id 'display' and buttons "
                             "for the digits 0-9 and + - * / =. Create tests/page.test.js (node:test + node:assert) that "
                             "reads index.html and asserts the title and the display element are present.",
                 depends_on=[], files=["package.json", "index.html", "tests/page.test.js"],
                 acceptance_criteria=["npm test passes", "index.html has the title and the display element"],
                 verify_commands=["npm test"]),
        PlanTask(id="T2", phase="P2", title="Add the arithmetic module",
                 description="Create src/calc.js exporting add, subtract, multiply and divide (divide by zero throws an "
                             "Error with the message 'Cannot divide by zero'). Create tests/calc.test.js covering each "
                             "function and the division error. Do not change tests/page.test.js.",
                 depends_on=["T1"], files=["src/calc.js", "tests/calc.test.js"],
                 acceptance_criteria=["all four operations correct", "divide by zero throws"],
                 verify_commands=["node --test tests/calc.test.js", "npm test"]),
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

markdown = render_plan_markdown(TRIVIAL_PLAN, cached.get("project_name", ""), 0, "verify_m8 (trivial plan)")
approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
values = {k: v for k, v in cached.items() if k not in ("implementation_log", "implementation_cost_usd", "workspace_dir",
                                                       "current_task_id", "error", "completed_at", "metrics")}
values |= {"implementation_plan": TRIVIAL_PLAN.model_dump(mode="json"), "plan_markdown": markdown,
           "implementation_tasks": tasks_from_plan(TRIVIAL_PLAN), "plan_review_route": "approved",
           "plan_approved_at": approved_at, "plan_approved_hash": plan_hash(markdown), "status": "reporting"}
print(f"implementer model: {settings.implementer_model} (effort {settings.implementer_effort})")
check(plan_is_approved(values), "the trivial plan is approved (plan hash + brief hash) like plan_review_router does")

thread_id = f"verify-m8-{int(time.time())}"
config = {"configurable": {"thread_id": thread_id}}
graph = build_graph(InMemorySaver())
t0 = time.monotonic()
with session_mode("full"):
    graph.update_state(config, values, as_node="plan_review_router")
    print(f"next node after the approval: {graph.get_state(config).next}")
    for chunk in graph.stream(None, config, stream_mode="custom"):
        print("   ", chunk.get("message") if isinstance(chunk, dict) else chunk)
state = dict(graph.get_state(config).values)
print(f"\nsession: {time.monotonic() - t0:.0f}s, status {state.get('status')}\n")

print("1. tasks")
tasks = state.get("implementation_tasks", [])
for t in tasks:
    r = t.get("result") or {}
    agent = r.get("agent") or {}
    check(t["status"] == "done", f"{t['id']} {t['status']} after {t['attempts']} attempt(s): verify "
          f"{[(v['command'], v['exit_code']) for v in r.get('verify', [])]}, {agent.get('turns')} turns, "
          f"${agent.get('cost_usd')}, {agent.get('seconds')}s, files {r.get('files_changed')}")
open_issues = (state.get("brief_validation") or {}).get("open_issues") or []
conditional = bool((state.get("final_report") or {}).get("is_conditional"))
built_ok = state.get("metrics", {}).get("tasks", {}).get("done") == len(tasks)
expected = "completed_with_uncertainty" if (conditional or open_issues) else "completed"
check(built_ok and state.get("status") == expected,
      f"session status: {state.get('status')} (expected {expected}: build {state.get('metrics', {}).get('tasks')}, "
      f"cached report conditional={conditional}, brief open issues={len(open_issues)})")
check(state.get("models_used", {}).get("implementer") == settings.implementer_model,
      f"implementer model used: {state.get('models_used', {}).get('implementer')}")
check(state.get("implementation_cost_usd", 0) > 0, f"cost recorded: ${state.get('implementation_cost_usd')}")

print("\n2. independent re-check")
ws = workspace_for(thread_id)
for t in TRIVIAL_PLAN.tasks:
    for command in t.verify_commands:
        r = sandbox.run(ws, command, label="verify_m8-recheck")
        check(r.ok, f"re-run now: {command} → {r.summary()}")
files = sorted(str(p.relative_to(ws.app)) for p in ws.app.rglob("*") if p.is_file())
check({"package.json", "index.html", "src/calc.js", "tests/calc.test.js", "tests/page.test.js"} <= set(files),
      f"files in app/: {files}")
key = settings.anthropic_api_key.get_secret_value()
check(not any(key in (ws.app / f).read_text(errors="ignore") for f in files), "no file in app/ contains the API key")
logs = {p.name: p.read_text() for p in ws.logs.glob("T*.log")}
denied = [line for text in logs.values() for line in text.splitlines() if "DENIED" in line]
check(bool(logs), f"agent logs: {sorted(logs)}; denied calls: {denied or 'none'}")
check(git_status() == git_before, "ai-lab-2's own git status is unchanged")

print(f"\nworkspace kept for inspection: {ws.root}")
print(f"M8 VERIFY: {'PASS' if not failures else 'FAIL'}")
for f in failures:
    print(f"  - {f}")
sys.exit(1 if failures else 0)
