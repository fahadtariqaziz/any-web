"""M12: browser tests (workspace/e2e.py + the e2e_check node). Report parsing, the builder-owned config, skip reasons,
and the graph loop E1 (write tests) → fix task (a test failed) → passed, with Playwright runs faked (pytest has no
npm network); the coding agent is the conftest FakeAgent. A REAL Playwright run is in scripts/verify_m12.py."""

import json

import pytest

from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes import implementer as I
from ai_decision_arena.workspace import e2e, sandbox
from ai_decision_arena.workspace.paths import create_workspace

from tests.conftest import build_plan
from tests.test_delivery import reply, to_preview

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def report_json(*specs) -> dict:
    """A Playwright JSON report: one file suite with a describe block holding the given (title, status, error) specs."""
    def spec(title, status, error):
        results = [{"status": "failed", "error": {"message": f"\x1b[31m{error}\x1b[39m"}}] if error else [{"status": "passed"}]
        return {"title": title, "file": "flows.e2e.mjs", "line": 3, "tests": [{"status": status, "results": results}]}
    return {"suites": [{"title": "flows.e2e.mjs", "file": "flows.e2e.mjs", "specs": [],
                        "suites": [{"title": "habits", "specs": [spec(*s) for s in specs]}]}]}


def test_parse_report_counts_outcomes_and_strips_colours():
    parsed = e2e.parse_report(report_json(("adds a habit", "expected", ""), ("ticks it", "unexpected", "Expected: 1"),
                                          ("streak", "flaky", "first try failed")))
    assert (parsed["total"], parsed["passed"], parsed["failed"], parsed["flaky"]) == (3, 1, 1, 1)
    failed = next(t for t in parsed["tests"] if t["status"] == "failed")
    assert failed["title"] == "habits › ticks it" and failed["error"] == "Expected: 1" and failed["file"] == "flows.e2e.mjs"
    assert next(t for t in parsed["tests"] if t["status"] == "passed")["error"] == ""


@pytest.fixture
def chrome(monkeypatch):
    monkeypatch.setattr(get_settings(), "e2e_check", True)
    monkeypatch.setattr(e2e.render_check, "find_browser", lambda: CHROME)


def test_skip_reasons(tmp_path, monkeypatch, chrome):
    ws = create_workspace("e2e-skip", tmp_path)
    plan = build_plan("", "")
    assert "package.json" in e2e.skip_reason(ws, plan)
    (ws.app / "package.json").write_text("{}")
    assert e2e.skip_reason(ws, plan) is None
    monkeypatch.setattr(e2e.render_check, "find_browser", lambda: None)
    assert "Chrome" in e2e.skip_reason(ws, plan)
    monkeypatch.setattr(get_settings(), "e2e_check", False)
    assert "disabled" in e2e.skip_reason(ws, plan)
    assert e2e.run(ws, plan) == {"status": "skipped", "reason": "browser tests are disabled (E2E_CHECK=false)"}


def test_config_is_owned_by_the_builder(tmp_path, chrome):
    ws = create_workspace("e2e-config", tmp_path)
    port = e2e.write_config(ws, build_plan("", ""))
    low, high = (int(p) for p in get_settings().e2e_port_range.split("-"))
    text = (ws.app / e2e.CONFIG_FILE).read_text()
    assert low <= port <= high and f"process.env.E2E_PORT || '{port}'" in text
    assert "command: `python3 -m http.server ${port} --bind 127.0.0.1`" in text       # the plan's dev command
    assert "channel: 'chrome'" in text and "testMatch: '**/*.e2e.{mjs,js}'" in text and "reuseExistingServer: false" in text
    assert e2e.browser_option("/usr/bin/chromium") == 'launchOptions: { executablePath: "/usr/bin/chromium" }, '


def test_spec_files_only_match_the_e2e_suffix(tmp_path):
    ws = create_workspace("e2e-specs", tmp_path)
    for name in ("e2e/flows.e2e.mjs", "e2e/sub/more.e2e.js", "e2e/helpers.mjs", "src/app.spec.js"):
        (ws.app / name).parent.mkdir(parents=True, exist_ok=True)
        (ws.app / name).write_text("//")
    assert e2e.spec_files(ws) == ["e2e/flows.e2e.mjs", "e2e/sub/more.e2e.js"]


def test_playwright_gets_the_long_timeout():
    settings = get_settings()
    assert sandbox.default_timeout(["npx", "playwright", "test"]) == settings.e2e_timeout_seconds
    assert sandbox.default_timeout(["npx", "vitest", "run"]) == settings.command_timeout_seconds


def test_task_kinds_pick_the_browser_test_skill():
    e2e_task = S.PlanTask(id="E1", phase="e2e", title="t", description="d", depends_on=[], files=[],
                          acceptance_criteria=["a"], verify_commands=[e2e.COMMAND])
    fix = e2e_task.model_copy(update={"id": "F1", "phase": "fix"})
    assert I.task_kinds(e2e_task, None) == ["e2e"] and I.task_kinds(fix, None) == ["fix", "e2e"]
    assert I.task_kinds(e2e_task.model_copy(update={"verify_commands": ["ls"], "phase": "P1"}), {"x": 1}) == ["retry"]


class FakePlaywright:
    """Replaces e2e.run: returns the scripted statuses in order (the last one repeats)."""

    def __init__(self, *statuses: str) -> None:
        self.statuses, self.calls = list(statuses), 0

    def __call__(self, ws, plan, label="e2e"):
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        tests = [{"title": "adds a habit", "file": "e2e/habits.e2e.mjs", "line": 3,
                  "status": "passed" if status == "passed" else "failed",
                  "error": "" if status == "passed" else "Expected: \"1 habit\"\nReceived: \"0 habits\""}]
        return {"status": status, "reason": "" if status == "passed" else "1 of 1 browser test(s) failed",
                "total": 1, "passed": int(status == "passed"), "failed": int(status != "passed"), "flaky": 0,
                "skipped": 0, "tests": tests, "seconds": 1.0, "output": "", "command": e2e.COMMAND}


@pytest.fixture
def e2e_graph(monkeypatch, chrome, fake_llm):
    """FakeAgent writes the spec in E1; the agent's `npx playwright test` verify is answered as passing (no npm)."""
    fake_llm.agent.writes = {"E1": ["e2e/habits.e2e.mjs"]}
    real_verify = I.run_verify

    def run_verify(ws, task):
        if e2e.COMMAND in task.verify_commands:
            return [{"command": e2e.COMMAND, "ok": True, "exit_code": 0, "summary": "exit 0", "output": ""}]
        return real_verify(ws, task)
    monkeypatch.setattr(I, "run_verify", run_verify)


def test_e1_writes_the_tests_then_a_failing_test_gets_a_fix_task(graph, fake_llm, fake_search, e2e_graph, monkeypatch):
    runs = FakePlaywright("failed", "passed")
    monkeypatch.setattr(e2e, "run", runs)
    state, snapshot = to_preview(graph, "e2e-loop")
    ids = [t["id"] for t in state["implementation_tasks"]]
    assert ids == ["T1", "T2", "E1", "F1"] and all(t["status"] == "done" for t in state["implementation_tasks"])
    e1, f1 = state["implementation_tasks"][2], state["implementation_tasks"][3]
    assert e1["phase"] == "e2e" and e1["spec"]["verify_commands"] == [e2e.COMMAND]
    assert f1["title"] == "Fix the failing browser tests" and f1["spec"]["verify_commands"] == [e2e.COMMAND]
    assert "<untrusted>" in f1["spec"]["description"] and "0 habits" in f1["spec"]["description"]
    prompts = {c["task"]: c["prompt"] for c in fake_llm.agent.calls}
    assert 'name="browser-e2e-testing"' in prompts["E1"] and 'name="failure-triage"' not in prompts["E1"]
    assert 'name="browser-e2e-testing"' in prompts["F1"] and 'name="failure-triage"' in prompts["F1"]
    assert 'name="browser-e2e-testing"' not in prompts["T1"]
    assert (ws_config := create_workspace("e2e-loop").app / e2e.CONFIG_FILE).is_file(), ws_config
    assert runs.calls == 2 and state["e2e_results"]["status"] == "passed" and state["e2e_results"]["round"] == 2
    assert state["e2e_fix_round"] == 1 and snapshot.next == ("await_change_request",)
    assert snapshot.interrupts[0].value["e2e"]["status"] == "passed"


def test_failing_browser_tests_stop_after_the_fix_rounds_and_a_change_resets_them(graph, fake_llm, fake_search,
                                                                                    e2e_graph, monkeypatch):
    runs = FakePlaywright("failed")
    monkeypatch.setattr(e2e, "run", runs)
    state, snapshot = to_preview(graph, "e2e-cap")
    rounds = get_settings().max_e2e_fix_rounds
    fixes = [t for t in state["implementation_tasks"] if t["id"].startswith("F")]
    assert len(fixes) == rounds and runs.calls == rounds + 1 and state["e2e_fix_round"] == rounds
    assert state["e2e_results"]["status"] == "failed" and snapshot.next == ("await_change_request",)
    assert sum(t["id"].startswith("E") for t in state["implementation_tasks"]) == 1       # tests written once
    state, snapshot = reply(graph, "e2e-cap", action="change", request="Make the header blue")
    assert runs.calls == 2 * rounds + 2 and state["e2e_fix_round"] == rounds              # reset to 0, then used up again
    assert snapshot.next == ("await_change_request",)


def test_no_browser_tests_for_a_project_without_package_json(graph, fake_llm, fake_search, chrome, monkeypatch):
    fake_llm.agent.skip = {"T1"}
    fake_llm.agent.writes = {"F1": ["src/main.js"]}                 # never package.json: the build check fails ...
    monkeypatch.setattr(get_settings(), "max_build_fix_rounds", 0)  # ... and the preview starts anyway
    state, snapshot = to_preview(graph, "e2e-none")
    assert state["e2e_results"]["status"] == "skipped" and "package.json" in state["e2e_results"]["reason"]
    assert not any(t["id"].startswith("E") for t in state["implementation_tasks"])
    assert snapshot.next == ("await_change_request",)


def test_run_reports_an_error_when_playwright_writes_no_report(tmp_path, chrome, monkeypatch):
    ws = create_workspace("e2e-error", tmp_path)
    (ws.app / "package.json").write_text(json.dumps({"name": "x"}))
    (ws.app / "e2e").mkdir()
    (ws.app / "e2e" / "a.e2e.mjs").write_text("//")
    result = sandbox.CommandResult(command=e2e.COMMAND, ok=False, exit_code=1, stdout_tail="",
                                   stderr_tail="Error: Cannot find module '@playwright/test'", duration_seconds=0.1)
    monkeypatch.setattr(e2e.sandbox, "run", lambda *a, **k: result)
    out = e2e.run(ws, build_plan("", ""))
    assert out["status"] == "error" and "no report" in out["reason"] and "@playwright/test" in out["output"]
    assert "Cannot find module" in e2e.failure_listing(out)
