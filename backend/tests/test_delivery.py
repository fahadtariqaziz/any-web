"""M9: build check (+ fix rounds), preview (a real dev server), change requests (change / replan / finish), caps,
the idle stop. The coding agent is the conftest FakeAgent; commands and the dev server run for real (python3)."""

import time

import httpx
import pytest
from langgraph.types import Command

from ai_decision_arena import graph as G
from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.workspace.processes import IdleStopper, now

from tests.conftest import build_plan
from tests.test_plan import to_plan_review


def to_preview(graph, thread_id: str):
    """Start a session and approve everything up to the preview pause."""
    to_plan_review(graph, thread_id)
    return reply(graph, thread_id, action="approve")


def reply(graph, thread_id: str, **body):
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume=body), config)
    snapshot = graph.get_state(config)
    return dict(snapshot.values), snapshot


def test_preview_is_running_after_a_passing_build(graph, fake_llm, fake_search):
    state, snapshot = to_preview(graph, "d-ok")
    assert snapshot.next == ("await_change_request",)
    payload = snapshot.interrupts[0].value
    assert payload["type"] == "change_request" and payload["round"] == 1 and payload["changes_allowed"]
    assert state["build_results"]["passed"] and state["build_results"]["steps"][0]["command"] == "ls package.json"
    preview = state["preview"]
    assert preview["state"] == "ready" and httpx.get(preview["url"], timeout=5).status_code == 200
    assert [t["status"] for t in payload["tasks"]] == ["done", "done"]
    state, snapshot = reply(graph, "d-ok", action="finish")
    assert snapshot.next == () and state["status"] == "completed" and state["metrics"]["preview_state"] == "ready"


def test_failing_build_gets_a_fix_task_that_can_fix_it(graph, fake_llm, fake_search):
    fake_llm.agent.skip = {"T1"}                        # package.json never written by T1 ...
    fake_llm.agent.writes = {"F1": ["package.json"]}    # ... the fix task writes it
    state, snapshot = to_preview(graph, "d-fix")
    fix = next(t for t in state["implementation_tasks"] if t["id"] == "F1")
    assert fix["status"] == "done" and fix["spec"]["verify_commands"] == ["ls package.json"]
    assert "<untrusted>" in fix["spec"]["description"] and "No such file" in fix["spec"]["description"]
    assert state["build_results"]["round"] == 2 and state["build_results"]["passed"]
    assert state["build_fix_round"] == 1 and snapshot.next == ("await_change_request",)


def test_fix_rounds_are_capped_then_the_preview_shows_the_result(graph, fake_llm, fake_search):
    fake_llm.agent.skip = {"T1"}
    state, snapshot = to_preview(graph, "d-cap")
    fixes = [t for t in state["implementation_tasks"] if t["id"].startswith("F")]
    assert len(fixes) == get_settings().max_build_fix_rounds and all(f["status"] == "failed" for f in fixes)
    assert state["build_results"]["round"] == get_settings().max_build_fix_rounds + 1
    assert not state["build_results"]["passed"] and snapshot.next == ("await_change_request",)
    state, _ = reply(graph, "d-cap", action="finish")
    assert state["status"] == "completed_with_uncertainty" and state["metrics"]["build_passed"] is False


def test_change_request_adds_a_task_rebuilds_and_restarts_the_preview(graph, fake_llm, fake_search):
    state, _ = to_preview(graph, "d-change")
    first_pid = state["preview"]["pid"]
    state, snapshot = reply(graph, "d-change", action="change", request="Add a dark mode toggle")
    change = state["implementation_tasks"][-1]
    assert change["id"] == "C1" and change["status"] == "done"
    assert change["spec"]["verify_commands"] == ["ls package.json"]                 # the plan's test commands
    assert "Add a dark mode toggle" in fake_llm.agent.calls[-1]["prompt"]
    assert state["build_results"]["round"] == 2 and state["preview"]["state"] == "ready"
    assert state["preview"]["pid"] != first_pid                                       # refreshed after the change
    assert snapshot.next == ("await_change_request",) and snapshot.interrupts[0].value["round"] == 2
    state, _ = reply(graph, "d-change", action="finish")
    assert state["metrics"]["change_requests"] == 2


def test_replan_goes_back_to_the_planner_and_needs_a_new_approval(graph, fake_llm, fake_search):
    to_preview(graph, "d-replan")
    plans_before = fake_llm.count("ImplementationPlan")
    state, snapshot = reply(graph, "d-replan", action="replan", request="Use a SQLite backend instead")
    assert fake_llm.count("ImplementationPlan") == plans_before + 1
    planner_call = [k for k in fake_llm.kwargs if k["schema"].__name__ == "ImplementationPlan"][-1]
    assert "Use a SQLite backend instead" in planner_call["user"] and "<previous_plan>" in planner_call["user"]
    assert snapshot.next == ("await_plan_review",) and not state["plan_approved_at"]
    state, snapshot = reply(graph, "d-replan", action="approve")
    assert snapshot.next == ("await_change_request",) and state["plan_revision_count"] == 1


def test_change_request_cap(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_change_requests", 1)
    to_preview(graph, "d-limit")
    _, snapshot = reply(graph, "d-limit", action="change", request="Bigger buttons")
    payload = snapshot.interrupts[0].value
    assert payload["changes_allowed"] is False and payload["replan_allowed"] is False
    _, snapshot = reply(graph, "d-limit", action="change", request="Even bigger")
    assert "maximum number of change requests" in snapshot.interrupts[0].value["error"]
    state, snapshot = reply(graph, "d-limit", action="finish")
    assert snapshot.next == ()


def test_change_without_text_is_refused_by_the_node(graph, fake_llm, fake_search):
    to_preview(graph, "d-empty")
    _, snapshot = reply(graph, "d-empty", action="change", request=" ")
    assert "request is required" in snapshot.interrupts[0].value["error"]


def test_broken_dev_server_is_reported_not_hidden(graph, fake_llm, fake_search):
    def plan_with_broken_dev(system, user):
        plan = build_plan(system, user)
        return plan.model_copy(update={"commands": plan.commands.model_copy(
            update={"dev": "python3 -m http.server --this-flag-does-not-exist"})})
    fake_llm.overrides[S.ImplementationPlan] = plan_with_broken_dev
    state, snapshot = to_preview(graph, "d-broken")
    assert state["preview"]["state"] == "failed" and "exited (code 2)" in state["preview"]["last_error"]
    assert "unrecognized arguments" in state["preview"]["last_error"]                 # the server's own output
    assert snapshot.interrupts[0].value["preview"]["state"] == "failed"
    state, _ = reply(graph, "d-broken", action="finish")
    assert state["status"] == "completed_with_uncertainty" and state["metrics"]["preview_state"] == "failed"


def test_route_after_change_request(monkeypatch):
    assert G.route_after_change_request({"change_route": "finish"}) == "completion"
    assert G.route_after_change_request({"change_route": "replan"}) == "planner"
    assert G.route_after_change_request({"change_route": "change"}) == "await_change_request"   # not approved
    monkeypatch.setattr(G, "plan_is_approved", lambda state: True)
    assert G.route_after_change_request({"change_route": "change"}) == "implementer"


def test_idle_stopper_stops_previews_nobody_looks_at(graph, fake_llm, fake_search, process_manager, monkeypatch):
    state, _ = to_preview(graph, "d-idle")
    record = process_manager.store.get("d-idle")
    record.last_seen_at = now().replace(year=2000)
    process_manager.store.save(record)
    monkeypatch.setattr(get_settings(), "preview_idle_check_seconds", 0.05)
    stopper = IdleStopper(process_manager)
    stopper.start()
    try:
        deadline = time.monotonic() + 5
        while process_manager.status("d-idle").state != "stopped" and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        stopper.stop()
    assert process_manager.status("d-idle").state == "stopped"
    with pytest.raises(httpx.HTTPError):
        httpx.get(state["preview"]["url"], timeout=2)
