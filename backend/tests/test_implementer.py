"""M8: implementer (one task attempt per step), the agent's path guard, and the approval guard.

The coding agent is the conftest FakeAgent (writes the files a task lists); the task's verify commands run for REAL
in the sandbox (`ls <files>`), so "done" comes from exit codes here exactly as in production."""

import json
from pathlib import Path

import pytest

from ai_decision_arena import graph as G
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.implementer import SYSTEM_APPEND, pick_next_task
from ai_decision_arena.workspace.paths import create_workspace, tool_path_problem

from tests.test_plan import run_full, to_plan_review


def task(tid, deps=(), status="pending"):
    return {"id": tid, "title": tid, "phase": "P1", "depends_on": list(deps), "status": status, "attempts": 0,
            "result": None}


# --- task selection ------------------------------------------------------------------------------------------------

def test_pick_next_task_follows_dependencies():
    tasks = [task("T1", status="done"), task("T2", ["T1"]), task("T3", ["T2"])]
    assert pick_next_task(tasks) == 1
    tasks[1]["status"] = "done"
    assert pick_next_task(tasks) == 2


def test_failed_task_blocks_its_dependants_transitively():
    tasks = [task("T1", status="failed"), task("T2", ["T1"]), task("T3", ["T2"]), task("T4")]
    assert pick_next_task(tasks) == 3                      # independent work still runs
    assert [t["status"] for t in tasks] == ["failed", "blocked", "blocked", "pending"]
    assert "T1" in tasks[1]["result"]["reason"]


def test_nothing_ready_blocks_the_rest():
    tasks = [task("T1", ["T9"])]                           # cannot happen with a checked plan: the safety net
    assert pick_next_task(tasks) is None and tasks[0]["status"] == "blocked"


# --- the agent's file-tool guard ----------------------------------------------------------------------------------

def test_tool_path_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "generated_projects_dir", tmp_path)
    ws = create_workspace("guard")
    other = create_workspace("other")
    inside = str(ws.app / "src" / "a.js")
    assert tool_path_problem(ws, "Write", {"file_path": inside}) is None
    assert tool_path_problem(ws, "Read", {"file_path": "src/a.js"}) is None
    assert tool_path_problem(ws, "Grep", {"pattern": "x"}) is None                       # no path = cwd = app/
    for bad in (str(other.app / "x.js"), "/etc/passwd", str(ws.builder / "plan.json"), str(ws.app) + "/../outside",
                "../x", "~/.ssh/id_rsa"):
        assert tool_path_problem(ws, "Read", {"file_path": bad}), bad
    assert tool_path_problem(ws, "Glob", {"pattern": "../**/*"})
    assert tool_path_problem(ws, "Glob", {"pattern": "/etc/*"})
    assert tool_path_problem(ws, "Grep", {"pattern": "KEY", "path": "/Users"})
    (ws.app / "link").symlink_to(other.app)
    assert tool_path_problem(ws, "Read", {"file_path": str(ws.app / "link" / "x.js")})   # symlink escape


# --- the node in the graph -----------------------------------------------------------------------------------------

def test_approved_plan_is_implemented_task_by_task(graph, fake_llm, fake_search):
    state = run_full(graph, "impl-ok")
    tasks = state["implementation_tasks"]
    assert [t["status"] for t in tasks] == ["done", "done"] and [t["attempts"] for t in tasks] == [1, 1]
    assert [c["task"] for c in fake_llm.agent.calls] == ["T1", "T2"]
    assert all(c["model"] == get_settings().implementer_model for c in fake_llm.agent.calls)
    assert state["status"] == "completed" and state["implementation_cost_usd"] == pytest.approx(0.02)
    ws = Path(state["workspace_dir"])
    assert (ws / "app" / "src" / "habits.js").exists()
    assert json.loads((ws / ".builder" / "tasks.json").read_text())[1]["status"] == "done"
    assert (ws / ".builder" / "plan.md").read_text() == state["plan_markdown"]
    verify = tasks[0]["result"]["verify"]
    assert verify[0]["command"] == "ls package.json src/main.js" and verify[0]["ok"] and verify[0]["exit_code"] == 0
    assert tasks[0]["result"]["files_changed"] == ["package.json", "src/main.js"]
    assert len(state["implementation_log"]) == 2 and state["models_used"]["implementer"]


def test_prompt_carries_only_the_task_context(graph, fake_llm, fake_search):
    run_full(graph, "impl-prompt")
    first, second = fake_llm.agent.calls
    assert '"id": "T1"' in first["prompt"] and '"id": "T2"' not in first["prompt"].split("<task>")[1]
    assert '["ls src/habits.js"]' in second["prompt"] and "T1: Scaffold the project" in second["prompt"]
    assert "src/main.js" in second["prompt"].split("<existing_files>")[1]               # files of earlier tasks
    assert "<previous_attempt>" not in second["prompt"]
    assert first["system"] == SYSTEM_APPEND and "re-runs these commands itself" in SYSTEM_APPEND


def test_the_agents_claim_does_not_count_only_verify(graph, fake_llm, fake_search):
    fake_llm.agent.skip = {"T1"}                            # agent "succeeds" (ok=True) but writes nothing
    state = run_full(graph, "impl-fail")
    t1, t2 = state["implementation_tasks"]
    assert t1["status"] == "failed" and t1["attempts"] == get_settings().max_task_attempts
    assert t1["result"]["agent"]["ok"] and not t1["result"]["passed"]
    assert t1["result"]["verify"][0]["exit_code"] != 0 and "No such file" in t1["result"]["verify"][0]["output"]
    assert t2["status"] == "blocked" and [c["task"] for c in fake_llm.agent.calls] == ["T1", "T1"]
    assert state["status"] == "completed_with_uncertainty" and state["metrics"]["tasks"]["failed"] == 1


def test_retry_gets_the_failing_output_and_can_pass(graph, fake_llm, fake_search):
    fake_llm.agent.fail_once = {"T2"}
    state = run_full(graph, "impl-retry")
    t2 = state["implementation_tasks"][1]
    assert t2["status"] == "done" and t2["attempts"] == 2
    retry_prompt = fake_llm.agent.calls[-1]["prompt"]
    assert "<previous_attempt>" in retry_prompt and "ls src/habits.js" in retry_prompt.split("<previous_attempt>")[1]
    assert [e["ok"] for e in state["implementation_log"]] == [True, False, True]


def test_session_budget_stops_new_attempts(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "implementation_budget_usd", 0.005)       # first attempt costs 0.01
    state = run_full(graph, "impl-budget")
    assert [t["status"] for t in state["implementation_tasks"]] == ["done", "skipped"]
    assert "budget" in state["implementation_tasks"][1]["result"]["reason"]
    assert len(fake_llm.agent.calls) == 1


def test_implementer_refuses_without_both_approvals(graph, fake_llm, fake_search):
    to_plan_review(graph, "impl-guard")
    config = {"configurable": {"thread_id": "impl-guard"}}
    graph.update_state(config, {"plan_review_route": "approved", "plan_approved_at": "2026-10-25T00:00:00+00:00",
                                "plan_approved_hash": "not-the-hash"}, as_node="plan_review_router")
    assert graph.get_state(config).next == ("await_plan_review",)      # the route refuses, back to the review
    from ai_decision_arena.nodes.implementer import implementer_node
    state = dict(graph.get_state(config).values)
    with pytest.raises(RuntimeError, match="not approved"):
        implementer_node(state)
    assert fake_llm.agent.calls == []


def test_route_after_implementer(monkeypatch):
    assert G.route_after_implementer({"implementation_tasks": [task("T1")]}) == "completion"   # not approved
    monkeypatch.setattr(G, "plan_is_approved", lambda state: True)
    assert G.route_after_implementer({"implementation_tasks": [task("T1")]}) == "implementer"
    assert G.route_after_implementer({"implementation_tasks": [task("T1", status="done")]}) == "completion"
