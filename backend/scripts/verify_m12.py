"""M12 live check: browser tests with Playwright (workspace/e2e.py), REAL npm + REAL Chrome through the builder's own
sandbox. Free by default (no model call); `--agent` adds one real coding-agent task (~$0.20-0.50, Sonnet).

Run from the backend/ folder (needs network for `npm install -D @playwright/test` and Google Chrome / Chromium):
    uv run python scripts/verify_m12.py [--agent]

1. Passing flows: a small counter app (static, served by the plan's dev command `python3 -m http.server {port}`,
   IPv4) + two e2e/*.e2e.mjs specs → e2e.run() installs nothing itself, writes the builder-owned config, runs
   `npx playwright test` in the sandbox → status "passed", 2/2 from Playwright's JSON report, a free port from
   e2e_port_range, the config uses the installed Chrome (no browser download).
2. A broken app (the + button stops counting) → status "failed", the failing test is named, its error says what
   was expected / received, failure_listing() is what a fix task would get.
3. A Vite-like dev server (Node, listening on "localhost", as Vite does) → "passed": the localhost URL works for
   both IPv4 and IPv6 bindings.
4. Unit runners are not confused: `node --test` in the same project (default patterns) does not pick up the
   *.e2e.mjs files (exit 0 with zero e2e tests run).
5. (--agent) The coding agent writes the browser tests itself for a small calculator (the E1 task's description
   and the browser-e2e-testing skill), then Python runs them: passed, user-facing locators, no sleeps.
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ai_decision_arena import schemas as S
from ai_decision_arena.workspace import e2e, render_check, sandbox
from ai_decision_arena.workspace.paths import create_workspace

FAILED: list[str] = []


def check(ok: bool, label: str) -> None:
    print(("✅ " if ok else "❌ ") + label)
    if not ok:
        FAILED.append(label)


def plan(dev: str) -> S.ImplementationPlan:
    """Only what the browser tests read (the dev command, the stack); the planner's checks are not the subject here."""
    return S.ImplementationPlan.model_construct(tech_stack=["HTML", "JavaScript"],
                                                commands=S.PlanCommands(install=[], test=[], build=[], dev=dev))


COUNTER = """<!doctype html><html><head><title>Counter</title></head><body>
<h1>Counter</h1><p>Count: <output id="count" aria-label="count">0</output></p>
<button onclick="add({step})">+</button> <button onclick="reset()">Reset</button>
<script>let n = 0; const out = document.getElementById('count');
function add(s) {{ n += s; out.textContent = String(n); }} function reset() {{ n = 0; out.textContent = '0'; }}</script>
</body></html>"""

SPEC = """import { test, expect } from '@playwright/test';

test.describe('counter', () => {
  test('counts up when the user presses +', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: '+' }).click();
    await page.getByRole('button', { name: '+' }).click();
    await expect(page.getByLabel('count')).toHaveText('2');
  });

  test('reset brings the count back to zero', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: '+' }).click();
    await page.getByRole('button', { name: 'Reset' }).click();
    await expect(page.getByLabel('count')).toHaveText('0');
  });
});
"""

LOCALHOST_SERVER = """import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
createServer((req, res) => { res.setHeader('content-type', 'text/html'); res.end(readFileSync('index.html')); })
  .listen(Number(process.env.PORT), 'localhost');
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="store_true", help="also run one real coding-agent task (~$0.20-0.50)")
    args = parser.parse_args()
    browser = render_check.find_browser()
    if not browser or not shutil.which("npm"):
        print("❌ needs Chrome / Chromium and npm")
        return 1
    root = Path(tempfile.mkdtemp(prefix="verify-m12-"))
    ws = create_workspace("m12", root)
    (ws.app / "package.json").write_text(json.dumps({"name": "m12-counter", "private": True, "type": "module",
                                                     "scripts": {"test": "node --test"}}))
    (ws.app / "index.html").write_text(COUNTER.format(step=1))
    (ws.app / "e2e").mkdir()
    (ws.app / "e2e" / "counter.e2e.mjs").write_text(SPEC)
    install = sandbox.run(ws, "npm install -D @playwright/test", label="m12-install")
    check(install.ok, f"npm install -D @playwright/test in the sandbox ({install.summary()})")
    if not install.ok:
        print(install.stderr_tail[-1500:])
        return 1
    check(not any((ws.home / d).exists() for d in ("Library/Caches/ms-playwright", ".cache/ms-playwright")),
          "no browser was downloaded (the installed Chrome is used)")

    print("\n— 1. passing flows (python http.server, 127.0.0.1)")
    static = plan("python3 -m http.server {port} --bind 127.0.0.1")
    r = e2e.run(ws, static)
    print("  ", e2e.summary(r))
    check(r["status"] == "passed" and r["total"] == 2 and r["passed"] == 2, f"status passed, 2/2 (got {r['status']}, "
          f"{r.get('passed')}/{r.get('total')}{', ' + r.get('reason', '') if r['status'] != 'passed' else ''})")
    low, high = (int(p) for p in e2e.get_settings().e2e_port_range.split("-"))
    check(low <= r.get("port", 0) <= high, f"Playwright's dev server on port {r.get('port')} (e2e_port_range)")
    config = (ws.app / e2e.CONFIG_FILE).read_text()
    check(("channel: 'chrome'" in config) or ("executablePath" in config), f"config uses the installed browser ({browser})")
    titles = [t["title"] for t in r.get("tests", [])]
    check(titles == ["counter › counts up when the user presses +", "counter › reset brings the count back to zero"],
          f"test titles from the report: {titles}")
    if r["status"] != "passed":
        print(r.get("output", "")[-2000:])

    print("\n— 2. a broken app (+ adds 0)")
    (ws.app / "index.html").write_text(COUNTER.format(step=0))
    r = e2e.run(ws, static)
    print("  ", e2e.summary(r))
    failing = [t for t in r.get("tests", []) if t["status"] == "failed"]
    check(r["status"] == "failed" and r["failed"] == 1, f"status failed, 1 failing test (got {r['status']}, {r.get('failed')})")
    check(bool(failing) and failing[0]["title"].endswith("counts up when the user presses +"),
          "the failing test is the counting flow")
    check(bool(failing) and "Expected" in failing[0]["error"] and '"2"' in failing[0]["error"] and '"0"' in failing[0]["error"],
          "its error says expected 2 / received 0")
    listing = e2e.failure_listing(r)
    check("counter.e2e.mjs" in listing and "\x1b[" not in listing, "fix-task listing: file + error, no colour codes")
    print("   " + listing.splitlines()[0])

    print("\n— 3. a Vite-like dev server listening on localhost (Node)")
    (ws.app / "index.html").write_text(COUNTER.format(step=1))
    (ws.app / "server.mjs").write_text(LOCALHOST_SERVER)
    r = e2e.run(ws, plan("node server.mjs"))
    print("  ", e2e.summary(r))
    check(r["status"] == "passed" and r["passed"] == 2, f"status passed with a localhost-bound server (got {r['status']})")
    if r["status"] != "passed":
        print(r.get("output", "")[-2000:])

    print("\n— 4. the unit test runner ignores the browser tests")
    unit = sandbox.run(ws, "npm test", label="m12-unit")
    out = unit.stdout_tail + unit.stderr_tail
    check(unit.ok and "counter.e2e" not in out and "@playwright/test" not in out,
          f"`npm test` (node --test) does not load e2e/*.e2e.mjs ({unit.summary()})")

    if args.agent:
        agent_section(root)
    print(f"\nproject kept for inspection: {ws.app}")
    print("M12 VERIFY: " + ("PASS" if not FAILED else f"FAIL ({len(FAILED)}: {'; '.join(FAILED)})"))
    return 0 if not FAILED else 1


CALCULATOR = """<!doctype html><html><head><title>Calculator</title></head><body>
<h1>Calculator</h1>
<label>First number <input id="a" type="number"></label>
<label>Second number <input id="b" type="number"></label>
<button id="add">Add</button>
<p role="status" id="result"></p>
<script>
document.getElementById('add').onclick = () => {
  const a = document.getElementById('a').value, b = document.getElementById('b').value;
  const out = document.getElementById('result');
  if (a === '' || b === '') { out.textContent = 'Enter both numbers'; return; }
  out.textContent = 'Result: ' + (Number(a) + Number(b));
};
</script></body></html>"""


def agent_section(root: Path) -> None:
    from ai_decision_arena.config import get_settings
    from ai_decision_arena.llm import resolve_model
    from ai_decision_arena.nodes.delivery import E2E_TASK_DESCRIPTION
    from ai_decision_arena.nodes.implementer import SYSTEM_APPEND, task_kinds
    from ai_decision_arena.skills import agent_skills_block
    from ai_decision_arena.workspace.agent import run_agent_task

    print("\n— 5. the coding agent writes the browser tests (real Sonnet task)")
    ws = create_workspace("m12-agent", root)
    (ws.app / "package.json").write_text(json.dumps({"name": "m12-calculator", "private": True, "type": "module"}))
    (ws.app / "index.html").write_text(CALCULATOR)
    p = plan("python3 -m http.server {port} --bind 127.0.0.1")
    e2e.write_config(ws, p)
    task = S.PlanTask(id="E1", phase="e2e", title="Write browser tests for the main user flows",
                      description=E2E_TASK_DESCRIPTION, depends_on=[], files=[],
                      acceptance_criteria=["One e2e/*.e2e.mjs test per main MVP user flow, driving the real UI"],
                      verify_commands=[e2e.COMMAND])
    brief = {"description": "A calculator that adds two numbers.",
             "mvp_features": ["Add two numbers and show the result", "Tell the user when a number is missing"],
             "out_of_scope": ["other operations"]}
    prompt = (f"<project_name>Calculator</project_name>\n<plan>{json.dumps({'tech_stack': p.tech_stack, 'commands': p.commands.model_dump()})}</plan>\n"
              f"<approved_brief_excerpt>{json.dumps(brief)}</approved_brief_excerpt>\n<finished_tasks>[\"T1: Calculator page\"]</finished_tasks>\n"
              f"<task>{json.dumps(task.model_dump(exclude={'verify_commands'}))}</task>\n<verify_commands>{json.dumps(task.verify_commands)}</verify_commands>\n"
              f"<existing_files>{json.dumps(['index.html', 'package.json', e2e.CONFIG_FILE])}</existing_files>\n"
              + agent_skills_block(" ".join(p.tech_stack), phase=task_kinds(task, None)) + "\n\nImplement task E1 now.")
    model, _ = resolve_model(get_settings().implementer_model)
    run = run_agent_task(ws, prompt, SYSTEM_APPEND, model=model, label="E1")
    print(f"   agent: {run.num_turns} turns, ${run.cost_usd:.3f}, {run.duration_seconds} s, ok={run.ok} {run.error or ''}")
    specs = e2e.spec_files(ws)
    check(bool(specs), f"the agent wrote browser tests: {specs}")
    r = e2e.run(ws, p)
    print("  ", e2e.summary(r))
    check(r["status"] == "passed" and r["total"] >= 2, f"Python's own run passes with >= 2 tests (got {r['status']}, {r.get('total')})")
    text = "\n".join((ws.app / s).read_text() for s in specs)
    check(bool(re.search(r"getBy(Role|Label|Text)", text)) and "waitForTimeout" not in text,
          "user-facing locators, no sleeps")
    check("Enter both numbers" in text, "the validation flow is tested too")
    check(e2e.CONFIG_FILE not in {c["target"].rsplit("/", 1)[-1] for c in run.tool_calls if c["tool"] in ("Write", "Edit")},
          "the agent left the builder's playwright.config.mjs alone")


if __name__ == "__main__":
    sys.exit(main())
