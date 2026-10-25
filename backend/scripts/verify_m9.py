"""M9 live check: build check → preview → a change request → preview refreshed → finish, with the REAL coding agent,
real commands, a real dev server and the real database (project_runtimes). Cheap: a tiny plan, no package download.

Starts from backend/.cache/plan_calculator.json (an approved brief) with a 2-task plan (a page served by a tiny Node
server that listens on $PORT, plus an arithmetic module), approved like plan_review_router does. Checks, from facts:
1. both tasks done, build check passed (exit codes), preview "ready", OUR GET of the preview URL → 200 with the page;
2. a change request ("add a footer ...") becomes task C1, is built and verified, the build check runs again, the
   preview restarts (new pid) and OUR GET now shows the footer;
3. finish → completion; the project_runtimes row is "ready"; ai-lab-2's git status unchanged; no API key in app/.
    uv run python -u scripts/verify_m9.py           (≈ 1–2 minutes, well under $1)
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_decision_arena.config import REPO_ROOT, get_settings, session_mode
from ai_decision_arena.db.repository import get_runtime
from ai_decision_arena.graph import build_graph
from ai_decision_arena.plan import plan_hash, render_plan_markdown, tasks_from_plan
from ai_decision_arena.schemas import ImplementationPlan, PlanCommands, PlanPhase, PlanTask
from ai_decision_arena.workspace.paths import workspace_for
from ai_decision_arena.workspace.processes import get_manager

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "plan_calculator.json"
FOOTER = "Built by AI Lab 2"
failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + message)
    if not ok:
        failures.append(message)


def git_status() -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True).stdout


def fetch(url: str) -> tuple[int | str, str]:
    try:
        r = httpx.get(url, timeout=10)
        return r.status_code, r.text
    except httpx.HTTPError as exc:
        return type(exc).__name__, ""


PLAN = ImplementationPlan(
    summary="A one-page calculator served by a tiny Node HTTP server, with node:test tests.",
    tech_stack=["Plain HTML + ES modules", "Node http module (no dependencies)", "node:test"],
    project_structure=["server.js: serves index.html and src/ on 127.0.0.1:$PORT", "index.html: the page",
                       "src/calc.js: arithmetic", "tests/*.test.js: node:test suites"],
    dependencies=["none (Node built-ins only)"], architecture="server.js serves static files; the page imports src/calc.js.",
    data_model="none", api_endpoints=["GET / → index.html", "GET /src/calc.js → the module"],
    frontend_components=["index.html: display + keypad"], backend_services=["server.js: static file server"],
    integrations=[], ai_components="none",
    phases=[PlanPhase(id="P1", name="Served page", goal="The page is served on $PORT and tested."),
            PlanPhase(id="P2", name="Arithmetic", goal="The arithmetic module works and is tested.")],
    tasks=[
        PlanTask(id="T1", phase="P1", title="Serve the static page",
                 description="Create package.json with \"type\": \"module\" and the scripts \"test\": \"node --test\" and "
                             "\"dev\": \"node server.js\". Create server.js: a node:http server listening on "
                             "127.0.0.1 and the port in process.env.PORT (exit with an error if PORT is missing), serving "
                             "index.html for / and files under src/ with the right content type, 404 otherwise. Create "
                             "index.html with the title 'Simple Calculator', an element with id 'display' and buttons for "
                             "0-9 and + - * / =. Create tests/page.test.js asserting the title and the display element.",
                 depends_on=[], files=["package.json", "server.js", "index.html", "tests/page.test.js"],
                 acceptance_criteria=["npm test passes", "npm run dev serves index.html on $PORT"],
                 verify_commands=["npm test"]),
        PlanTask(id="T2", phase="P2", title="Add the arithmetic module",
                 description="Create src/calc.js exporting add, subtract, multiply, divide (divide by zero throws Error "
                             "'Cannot divide by zero') and tests/calc.test.js covering all of them.",
                 depends_on=["T1"], files=["src/calc.js", "tests/calc.test.js"],
                 acceptance_criteria=["all operations correct", "divide by zero throws"],
                 verify_commands=["node --test tests/calc.test.js", "npm test"]),
    ],
    feature_coverage=[], testing_strategy=["node:test per module"],
    commands=PlanCommands(install=[], test=["npm test"], build=[], dev="npm run dev"),
    risks_and_decisions=["none"],
)

if not CACHE.exists():
    sys.exit(f"{CACHE} is missing: run scripts/verify_m6.py first.")
settings = get_settings()
cached = json.loads(CACHE.read_text())
git_before = git_status()
markdown = render_plan_markdown(PLAN, cached.get("project_name", ""), 0, "verify_m9 (tiny plan)")
values = {k: v for k, v in cached.items() if k not in ("implementation_log", "implementation_cost_usd", "workspace_dir",
                                                       "current_task_id", "error", "completed_at", "metrics")}
values |= {"implementation_plan": PLAN.model_dump(mode="json"), "plan_markdown": markdown,
           "implementation_tasks": tasks_from_plan(PLAN), "plan_review_route": "approved",
           "plan_approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "plan_approved_hash": plan_hash(markdown), "status": "reporting"}

thread_id = f"verify-m9-{int(time.time())}"
config = {"configurable": {"thread_id": thread_id}}
graph = build_graph(InMemorySaver())


def run(command) -> tuple[dict, object]:
    with session_mode("full"):
        for chunk in graph.stream(command, config, stream_mode="custom"):
            print("   ", chunk.get("message") if isinstance(chunk, dict) else chunk)
    snapshot = graph.get_state(config)
    return dict(snapshot.values), snapshot


t0 = time.monotonic()
with session_mode("full"):
    graph.update_state(config, values, as_node="plan_review_router")
state, snapshot = run(None)
print(f"\n{time.monotonic() - t0:.0f}s\n")

print("1. build → preview")
check(snapshot.next == ("await_change_request",), f"paused at {snapshot.next}")
check([t["status"] for t in state["implementation_tasks"]] == ["done", "done"],
      f"tasks: {[(t['id'], t['status'], t['attempts']) for t in state['implementation_tasks']]}")
build = state.get("build_results") or {}
check(build.get("passed") is True, f"build check {build.get('round')}: {[(s['command'], s['summary']) for s in build.get('steps', [])]}")
preview = state.get("preview") or {}
check(preview.get("state") == "ready", f"preview {preview.get('state')} {preview.get('url')} {preview.get('last_error') or ''}")
low, high = (int(x) for x in settings.preview_port_range.split("-"))
check(preview.get("port") is not None and low <= preview["port"] <= high, f"port {preview.get('port')} in {settings.preview_port_range}")
code, body = fetch(preview["url"]) if preview.get("url") else ("no url", "")
check(code == 200 and "Simple Calculator" in body, f"our GET {preview.get('url')} → {code}, page title present: {'Simple Calculator' in body}")
row = get_runtime(thread_id)
check(row is not None and row["state"] == "ready" and row["port"] == preview.get("port"), f"project_runtimes row: {row and row['state']}")
first_pid = preview.get("pid")

print("\n2. change request")
t0 = time.monotonic()
state, snapshot = run(Command(resume={"action": "change", "request": f"Add a footer to the page with the exact text: {FOOTER}. "
                                                                      "Add a test for it."}))
print(f"\n{time.monotonic() - t0:.0f}s\n")
change = state["implementation_tasks"][-1]
check(change["id"] == "C1" and change["status"] == "done", f"change task {change['id']}: {change['status']} after "
      f"{change['attempts']} attempt(s), verify {[(v['command'], v['exit_code']) for v in (change['result'] or {}).get('verify', [])]}")
check(state["build_results"]["round"] == 2 and state["build_results"]["passed"], f"build check {state['build_results']['round']} passed")
preview = state.get("preview") or {}
check(preview.get("state") == "ready" and preview.get("pid") != first_pid, f"preview restarted: pid {first_pid} → {preview.get('pid')}")
code, body = fetch(preview["url"]) if preview.get("url") else ("no url", "")
check(code == 200 and FOOTER in body, f"our GET {preview.get('url')} → {code}, footer present: {FOOTER in body}")
check(snapshot.next == ("await_change_request",) and snapshot.interrupts[0].value["round"] == 2, "paused again for round 2")

print("\n3. finish")
state, snapshot = run(Command(resume={"action": "finish"}))
check(snapshot.next == (), f"session ended: {state.get('status')}, metrics {json.dumps({k: state['metrics'].get(k) for k in ('tasks', 'build_passed', 'preview_state', 'change_requests', 'implementation_cost_usd')})}")
ws = workspace_for(thread_id)
key = settings.anthropic_api_key.get_secret_value()
files = [p for p in ws.app.rglob("*") if p.is_file() and "node_modules" not in p.parts]
check(not any(key in p.read_text(errors="ignore") for p in files), f"no API key in the {len(files)} files of app/")
check(git_status() == git_before, "ai-lab-2's own git status is unchanged")
stopped = get_manager().stop(thread_id, reason="verify done")
check(stopped is not None and stopped.state == "stopped" and fetch(preview["url"])[0] != 200, "preview stopped by the script afterwards")

print(f"\nworkspace kept for inspection: {ws.root}  (agent cost ${state.get('implementation_cost_usd')})")
print(f"M9 VERIFY: {'PASS' if not failures else 'FAIL'}")
for f in failures:
    print(f"  - {f}")
sys.exit(1 if failures else 0)
