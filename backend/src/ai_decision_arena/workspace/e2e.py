"""Browser end-to-end tests of the generated app (M12, Playwright): click through the user's flows in a real browser.

The build check proves the unit tests and the build pass; the render check proves the first screen draws. Neither
clicks a button, fills a form or follows a link. This module runs the app's own Playwright specs, written by the coding
agent for the brief's MVP flows, and reports facts from Playwright's JSON report, never from a model:

- the specs live in app/e2e/*.e2e.mjs: not *.spec / *.test and not in test/ or __tests__/, so the project's unit
  test runner (node --test, vitest, jest) and its type check never pick them up;
- playwright.config.mjs is OWNED BY THE BUILDER: rewritten before every run (a free port from e2e_port_range, the
  plan's dev command as Playwright's webServer, the browser, timeouts, the JSON report path). Playwright starts its
  own dev server: the tests never touch the user's running preview, and it runs WITHOUT the user's app settings
  (.builder/app.env), so a test can never write into the user's real Supabase / external service;
- the browser is the installed Chrome (channel "chrome", the same one the render check uses): nothing is downloaded
  (`npx playwright install` is never needed); `npm install -D @playwright/test` is the only dependency;
- the command runs through workspace.sandbox (same allowlist, env and process-group kill as every other command).

`run()` returns {status, reason, total, passed, failed, flaky, skipped, tests: [{title, file, status, error}],
output, port, seconds}. status: "passed" | "failed" (a test failed) | "error" (no report: Playwright missing, config
or syntax error, webServer did not start) | "skipped" (with a reason, see `skip_reason`).
"""

import json
import os
import re
import time

from ai_decision_arena.config import get_settings
from ai_decision_arena.schemas import ImplementationPlan
from ai_decision_arena.workspace import render_check, sandbox
from ai_decision_arena.workspace.paths import Workspace
from ai_decision_arena.workspace.processes import port_is_free

E2E_DIR = "e2e"
SPEC_SUFFIXES = (".e2e.mjs", ".e2e.js")
CONFIG_FILE = "playwright.config.mjs"
REPORT_FILE = "test-results/e2e-report.json"
COMMAND = "npx playwright test"
OUTPUT_CHARS = 3000
MAX_TESTS = 60
MAX_ERROR_CHARS = 700
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
GOOGLE_CHROME = "Google Chrome.app"

CONFIG_TEMPLATE = """// Written by the AI App Builder before every browser-test run: edits here are overwritten.
// Outside the builder: `npx playwright test` (uses your installed Chrome; set E2E_PORT if {port} is taken).
import {{ defineConfig }} from '@playwright/test';

const port = process.env.E2E_PORT || '{port}';

export default defineConfig({{
  testDir: './{e2e_dir}',
  testMatch: '**/*.e2e.{{mjs,js}}',
  timeout: {test_timeout_ms},
  expect: {{ timeout: 5000 }},
  retries: 1,
  workers: 1,
  reporter: [['json', {{ outputFile: '{report}' }}], ['line']],
  outputDir: 'test-results/artifacts',
  use: {{ baseURL: `http://localhost:${{port}}`, headless: true, {browser}trace: 'off', screenshot: 'off' }},
  webServer: {{
    command: {command},
    url: `http://localhost:${{port}}/`,
    timeout: {server_timeout_ms},
    reuseExistingServer: false,
    env: {{ PORT: port, BROWSER: 'none' }},
  }},
}});
"""


def spec_files(ws: Workspace) -> list[str]:
    folder = ws.app / E2E_DIR
    if not folder.is_dir():
        return []
    return sorted(str(p.relative_to(ws.app)) for p in folder.rglob("*")
                  if p.is_file() and p.name.endswith(SPEC_SUFFIXES) and "node_modules" not in p.parts)


def skip_reason(ws: Workspace, plan: ImplementationPlan) -> str | None:
    """Why browser tests cannot run for this project (None = they can)."""
    if not get_settings().e2e_check:
        return "browser tests are disabled (E2E_CHECK=false)"
    if not plan.commands.dev:
        return "the plan has no dev server command"
    if not (ws.app / "package.json").is_file():
        return "not a Node project (no package.json): browser tests need npm for @playwright/test"
    if not render_check.find_browser():
        return "no Chrome / Chromium installed for the browser tests"
    return None


def browser_option(path: str) -> str:
    """The installed Google Chrome by channel (portable when the project is downloaded); any other by path."""
    if GOOGLE_CHROME in path or os.path.basename(path) in ("google-chrome", "google-chrome-stable"):
        return "channel: 'chrome', "
    return f"launchOptions: {{ executablePath: {json.dumps(path)} }}, "


def free_port() -> int:
    low, high = (int(p) for p in get_settings().e2e_port_range.split("-"))
    for port in range(low, high + 1):
        if port_is_free(port):
            return port
    raise RuntimeError(f"no free port for the browser tests in {low}-{high}")


def write_config(ws: Workspace, plan: ImplementationPlan) -> int:
    """(Re)write the builder-owned Playwright config with a free port; returns the port."""
    settings = get_settings()
    port = free_port()
    command = plan.commands.dev.replace("{port}", "${port}")       # a JS template literal reads `port` at load time
    text = CONFIG_TEMPLATE.format(
        port=port, e2e_dir=E2E_DIR, report=REPORT_FILE, command="`" + command.replace("`", "\\`") + "`",
        browser=browser_option(render_check.find_browser() or ""),
        test_timeout_ms=int(settings.e2e_test_timeout_seconds * 1000),
        server_timeout_ms=int(settings.preview_health_timeout_seconds * 1000))
    (ws.app / CONFIG_FILE).write_text(text, encoding="utf-8")
    return port


def _strip(text: str) -> str:
    return ANSI_RE.sub("", text or "").strip()


def _walk(suite: dict, file: str = "", titles: tuple[str, ...] = ()):
    """(spec, file, describe titles). The top suite of a file is titled with the file name: not a describe."""
    if suite.get("file") and not file:
        file = suite["file"]
    elif suite.get("title"):
        titles = (*titles, suite["title"])
    for spec in suite.get("specs", []):
        yield spec, spec.get("file") or file, titles
    for child in suite.get("suites", []):
        yield from _walk(child, file, titles)


def parse_report(data: dict) -> dict:
    """Per-test outcome from Playwright's JSON reporter. A test that failed and then passed its retry is "flaky"
    (counted as passed, listed so it shows)."""
    tests = []
    for suite in data.get("suites", []):
        for spec, file, titles in _walk(suite):
            for test in spec.get("tests", []):
                status = {"expected": "passed", "unexpected": "failed"}.get(test.get("status", ""), test.get("status", ""))
                error = ""
                for result in test.get("results", []):
                    if result.get("error"):
                        error = _strip(result["error"].get("message") or result["error"].get("value") or "")
                tests.append({"title": " › ".join([*titles, spec.get("title", "")]),
                              "file": file, "line": spec.get("line"), "status": status,
                              "error": error[:MAX_ERROR_CHARS] if status != "passed" else ""})
    count = {s: sum(t["status"] == s for t in tests) for s in ("passed", "failed", "flaky", "skipped")}
    return {"total": len(tests), **count, "tests": tests[:MAX_TESTS]}


def run(ws: Workspace, plan: ImplementationPlan, label: str = "e2e") -> dict:
    """Write the config, run the specs in the sandbox, read the JSON report. Never raises for a failing app."""
    if reason := skip_reason(ws, plan):
        return {"status": "skipped", "reason": reason}
    specs = spec_files(ws)
    if not specs:
        return {"status": "skipped", "reason": f"no browser tests in {E2E_DIR}/ (*.e2e.mjs)"}
    port = write_config(ws, plan)
    report_path = ws.app / REPORT_FILE
    report_path.unlink(missing_ok=True)
    t0 = time.monotonic()
    r = sandbox.run(ws, COMMAND, timeout=get_settings().e2e_timeout_seconds, label=label)
    output = _strip(r.stdout_tail.strip() + "\n" + r.stderr_tail.strip())[-OUTPUT_CHARS:]
    base = {"command": COMMAND, "specs": specs, "port": port, "exit_code": r.exit_code,
            "seconds": round(time.monotonic() - t0, 1), "output": output}
    if not report_path.is_file():
        why = "timed out" if r.timed_out else "Playwright wrote no report"
        return base | {"status": "error", "reason": f"{why} ({r.summary()}): see the output", "total": 0, "passed": 0,
                       "failed": 0, "flaky": 0, "skipped": 0, "tests": []}
    try:
        parsed = parse_report(json.loads(report_path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return base | {"status": "error", "reason": f"unreadable report: {exc}", "total": 0, "passed": 0, "failed": 0,
                       "flaky": 0, "skipped": 0, "tests": []}
    # Facts: the exit code AND the report must agree that nothing failed; zero tests run is not a pass.
    passed = r.ok and parsed["failed"] == 0 and parsed["total"] > 0
    status = "passed" if passed else ("failed" if parsed["failed"] else "error")
    reason = "" if passed else (f"{parsed['failed']} of {parsed['total']} browser test(s) failed" if parsed["failed"]
                                else "no test ran" if not parsed["total"] else f"Playwright exited {r.exit_code}")
    return base | parsed | {"status": status, "reason": reason}


def summary(result: dict) -> str:
    status = result.get("status")
    if status == "skipped":
        return f"browser tests skipped: {result.get('reason', '')}"
    if status == "passed":
        flaky = f", {result['flaky']} flaky" if result.get("flaky") else ""
        return f"browser tests passed: {result['passed'] + result.get('flaky', 0)}/{result['total']}{flaky} ({result['seconds']} s)"
    return f"browser tests {status}: {result.get('reason', '')}"


def failure_listing(result: dict) -> str:
    """The failing tests with their errors (for a fix task; the caller wraps it in <untrusted>)."""
    failing = [t for t in result.get("tests", []) if t["status"] == "failed"]
    if not failing:
        return result.get("output", "")[-OUTPUT_CHARS:]
    return "\n\n".join(f"{t['file']}:{t['line']} › {t['title']}\n{t['error']}" for t in failing)[-OUTPUT_CHARS:]

