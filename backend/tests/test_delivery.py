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
    fix_prompt = next(c["prompt"] for c in fake_llm.agent.calls if c["task"] == "F1")
    assert 'name="failure-triage"' in fix_prompt and 'name="failure-triage"' not in fake_llm.agent.calls[0]["prompt"]
    assert state["build_results"]["round"] == 2 and state["build_results"]["passed"]
    assert state["build_fix_round"] == 1 and snapshot.next == ("await_change_request",)


def test_a_hard_coded_secret_fails_the_build_check_and_gets_its_own_fix_task(graph, fake_llm, fake_search):
    """Review 2026-10-29: the secret scan is a build-check step (Python, no model). The agent's rule "secrets come
    from the environment" is checked, not trusted; the fix task overwrites the file and the re-scan passes."""
    fake_llm.agent.writes = {"T1": ["src/keys.js"], "F1": ["src/keys.js"]}
    fake_llm.agent.contents = {"T1": {"src/keys.js": "export const key = 'AKIAZZZZZZZZZZZZZZZZ';\n"}}
    state, snapshot = to_preview(graph, "d-secret")
    fix = next(t for t in state["implementation_tasks"] if t["id"] == "F1")
    assert fix["spec"]["title"] == "Remove the hard-coded secret(s) from the source" and fix["status"] == "done"
    assert "src/keys.js:1: AWS access key (AKIA…ZZ)" in fix["spec"]["description"]
    assert "AKIAZZZZZZZZZZZZZZZZ" not in fix["spec"]["description"]                  # redacted, never the value
    assert fix["spec"]["verify_commands"] == ["ls package.json"]                       # the plan's test commands
    assert state["build_results"]["round"] == 2 and state["build_results"]["passed"]
    assert [s["phase"] for s in state["build_results"]["steps"]] == ["test"]          # round 2: scan clean, no step
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


def test_bigger_change_updates_the_brief_first_then_plans_only_the_new_work(graph, fake_llm, fake_search):
    to_preview(graph, "d-replan")
    state, _ = reply(graph, "d-replan", action="change", request="Add a percent key")      # C1, built and done
    built_files = {t["id"] for t in state["implementation_tasks"]}
    agent_calls = len(fake_llm.agent.calls)
    briefs_before = fake_llm.count("BriefPartOne")

    # 1. the request goes to the brief writer (edit of the approved brief), both approvals are cleared
    state, snapshot = reply(graph, "d-replan", action="replan", request="Make it a scientific calculator as well")
    assert snapshot.next == ("await_brief_review",)
    assert fake_llm.count("BriefPartOne") == briefs_before + 1
    writer_call = [k for k in fake_llm.kwargs if k["schema"].__name__ == "BriefPartOne"][-1]
    assert "Make it a scientific calculator as well" in writer_call["user"] and "<previous_draft>" in writer_call["user"]
    # the brief must not call already built changes out of scope
    # every agent (writer AND validator) sees the built change as the user's own statement (shared user block)
    validator_call = [k for k in fake_llm.kwargs if k["schema"].__name__ == "BriefReview"][-1]
    for call in (writer_call, validator_call):
        assert "<changes_built_after_approval>\n<change>Add a percent key</change>" in call["user"]
    assert not state["brief_approved_at"] and not state["plan_approved_at"]

    # the app is built: the brief can only be EDITED (no re-research / new proposal that would describe another app);
    # "auto" goes to wording without the routing LLM call, and the writer keeps the built stack
    payload = snapshot.interrupts[0].value
    assert payload["wording_only"] is True and payload["wording_only_reason"] == "built"
    _, snapshot = reply(graph, "d-replan", action="request_changes", feedback="Use another approach", target="proposal")
    assert "already built" in snapshot.interrupts[0].value["error"]
    routings, proposals = fake_llm.count("FeedbackRouting"), fake_llm.count("ProposerOutput")
    state, snapshot = reply(graph, "d-replan", action="request_changes", feedback="Keep the percent key in scope", target="auto")
    assert snapshot.next == ("await_brief_review",) and state["brief_feedback"][-1]["resolved_target"] == "wording"
    assert fake_llm.count("FeedbackRouting") == routings and fake_llm.count("ProposerOutput") == proposals
    writer_call = [k for k in fake_llm.kwargs if k["schema"].__name__ == "BriefPartOne"][-1]
    assert "<built_app>" in writer_call["user"] and "Vite (fast dev server)" in writer_call["user"]

    # 2. brief approved → the planner writes a plan EXTENSION on top of the built tasks
    state, snapshot = reply(graph, "d-replan", action="approve")
    assert snapshot.next == ("await_plan_review",)
    planner_call = [k for k in fake_llm.kwargs if k["schema"].__name__ == "PlanExtension"][-1]
    for part in ("<built_plan>", "<built_tasks>", "<project_files>", "Make it a scientific calculator as well"):
        assert part in planner_call["user"]
    assert '"src/main.js"' in planner_call["user"]                      # the real files of the built app
    tasks = {t["id"]: t["status"] for t in state["implementation_tasks"]}
    assert tasks == {**{i: "done" for i in built_files}, "T3": "pending"}  # built work kept (T1, T2, C1), only T3 is new
    payload = snapshot.interrupts[0].value
    assert payload["task_count"] == 3 and payload["new_task_count"] == 1 and payload["round"] == 2
    assert "Add a percent key" in planner_call["user"]                  # <later_changes>: the C1 request
    assert "1 new task (T3)" in state["plan_markdown"] and "T1. Scaffold the project** · *built*" in state["plan_markdown"]

    # 3. plan approved → the coding agent does ONLY the new task, then build check + preview again
    state, snapshot = reply(graph, "d-replan", action="approve")
    assert snapshot.next == ("await_change_request",)
    assert [c["task"] for c in fake_llm.agent.calls[agent_calls:]] == ["T3"]
    assert all(t["status"] == "done" for t in state["implementation_tasks"]) and state["build_results"]["passed"]


def test_a_plan_extension_must_merge_into_a_valid_plan():
    import pytest as _pytest

    from ai_decision_arena import schemas as S
    from ai_decision_arena.plan import extension_schema_for
    from tests.conftest import build_plan, build_plan_extension
    built = build_plan("", "<mvp_features>[\"Track habits\"]</mvp_features>")
    schema = extension_schema_for(["Track habits"], built)
    user = f"<mvp_features>[\"Track habits\"]</mvp_features><built_plan>{built.model_dump_json()}</built_plan>"
    good = build_plan_extension("", user)
    assert schema.model_validate(good.model_dump()).tasks[0].id == "T3"
    reused = good.model_dump() | {"tasks": [good.tasks[0].model_copy(update={"id": "T2"}).model_dump()]}
    with _pytest.raises(ValueError, match="must not reuse built task ids"):
        schema.model_validate(reused)
    bad_dep = good.model_dump() | {"tasks": [good.tasks[0].model_copy(update={"depends_on": ["T9"]}).model_dump()]}
    with _pytest.raises(ValueError, match="merged with the built tasks"):
        schema.model_validate(bad_dep)
    uncovered = good.model_dump() | {"feature_coverage": []}
    with _pytest.raises(ValueError, match="Missing: Track habits"):
        schema.model_validate(uncovered)
    assert S.PlanExtension.__name__ == "PlanExtension"


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
    assert G.route_after_change_request({"change_route": "replan"}) == "brief_writer"
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


# --- render check (headless Chrome after the dev server answers; faked here, real in test_render_check) ----------

def fake_render(monkeypatch, statuses: list[str]):
    """render_check.check returns these statuses in order (the last one repeats)."""
    from ai_decision_arena.workspace import render_check
    calls = []

    def check(url, timeout=None):
        status = statuses[min(len(calls), len(statuses) - 1)]
        calls.append(url)
        errors = {"blank": ["Uncaught Error: Missing Supabase configuration"],
                  "warnings": ["console.error: Failed to fetch"]}.get(status, [])
        return {"status": status, "errors": errors, "text_chars": 0 if status == "blank" else 42, "snippet": "",
                "at": "2026-10-27T00:00:00+00:00"}
    monkeypatch.setattr(render_check, "check", check)
    return calls


def test_blank_preview_gets_a_fix_task_then_is_checked_again(graph, fake_llm, fake_search, monkeypatch):
    calls = fake_render(monkeypatch, ["blank", "ok"])
    state, snapshot = to_preview(graph, "d-blank")
    fix = next(t for t in state["implementation_tasks"] if t["id"] == "F1")
    assert fix["status"] == "done" and "blank" in fix["title"]
    assert "<untrusted>Uncaught Error: Missing Supabase configuration</untrusted>" in fix["spec"]["description"]
    assert fix["spec"]["verify_commands"] == ["ls package.json"]                      # the plan's test commands
    assert len(calls) == 2 and state["preview"]["render"]["status"] == "ok"          # rebuilt, restarted, re-checked
    assert state["build_fix_round"] == 1 and snapshot.next == ("await_change_request",)
    assert snapshot.interrupts[0].value["preview"]["render"]["status"] == "ok"


def test_blank_preview_fix_rounds_are_capped(graph, fake_llm, fake_search, monkeypatch):
    calls = fake_render(monkeypatch, ["blank"])
    state, snapshot = to_preview(graph, "d-blank-cap")
    fixes = [t for t in state["implementation_tasks"] if t["id"].startswith("F")]
    assert len(fixes) == get_settings().max_build_fix_rounds
    assert len(calls) == get_settings().max_build_fix_rounds + 1
    assert state["preview"]["render"]["status"] == "blank" and snapshot.next == ("await_change_request",)


def test_render_warnings_do_not_add_a_task(graph, fake_llm, fake_search, monkeypatch):
    fake_render(monkeypatch, ["warnings"])
    state, snapshot = to_preview(graph, "d-warn")
    assert not any(t["id"].startswith("F") for t in state["implementation_tasks"])
    assert state["preview"]["render"]["status"] == "warnings" and snapshot.next == ("await_change_request",)
