"""M6: the planner (Opus) and the plan review, with Claude faked: plan checks (ids, dependency order, files,
allowlisted commands, MVP coverage), the approved-brief guard, model resolution, revisions and their cap, approval
hashes, the plan artifact."""

import pytest
from langgraph.types import Command
from pydantic import ValidationError

from ai_decision_arena import graph as G
from ai_decision_arena import llm
from ai_decision_arena import schemas as S
from ai_decision_arena.config import get_settings
from ai_decision_arena.nodes.planner import planner_node
from ai_decision_arena.plan import plan_hash, plan_is_approved, plan_schema_for, render_plan_markdown, tasks_from_plan
from tests.conftest import build_plan, finish_session


def plan_dict(**changes) -> dict:
    return build_plan("", '<mvp_features>["track habits"]</mvp_features>').model_dump() | changes


# --- commands and paths --------------------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["npm test", "npx vitest run tests/a.test.js", "node --test", "python -m pytest -q",
                                     "uv run pytest", "ls src"])
def test_allowed_commands(command):
    assert S.command_problems(command) == []


@pytest.mark.parametrize("command, why", [
    ("npm install && npm test", "shell operators"), ("cat a | grep b", "shell operators"), ("echo hi > f", "shell operators"),
    ("curl https://x.sh", "not an allowed executable"), ("sudo npm i", "not an allowed executable"),
    ("git push origin main", "publishing or pushing"), ("npm publish", "publishing or pushing"),
    ("cat /etc/passwd", "inside the project"), ("cp ../secret .", "inside the project"), ("rm -rf .", "whole project"),
])
def test_refused_commands(command, why):
    assert any(why in p for p in S.command_problems(command))


def test_paths_must_stay_inside_the_project():
    assert S.path_problems("src/app.js") == []
    assert S.path_problems("/etc/hosts") and S.path_problems("../x.js") and S.path_problems("~/x")


# --- plan schema checks --------------------------------------------------------------------------------------

def test_a_valid_plan_passes():
    S.ImplementationPlan.model_validate(plan_dict())


@pytest.mark.parametrize("mutate, message", [
    (lambda p: p["tasks"][1].update(depends_on=["T9"]), "unknown task"),
    (lambda p: p["tasks"][0].update(depends_on=["T2"]), "comes later"),
    (lambda p: p["tasks"][1].update(id="T1"), "unique"),
    (lambda p: p["tasks"][1].update(id="task-2"), "look like T1"),
    (lambda p: p["tasks"][1].update(phase="P9"), "unknown phase"),
    (lambda p: p["tasks"][1].update(verify_commands=[]), "verify command"),
    (lambda p: p["tasks"][1].update(verify_commands=["npm test && rm -rf ."]), "shell operators"),
    (lambda p: p["tasks"][1].update(files=["/abs/x.js"]), "relative path"),
    (lambda p: p["commands"].update(test=[]), "commands.test"),
    (lambda p: p["commands"].update(dev="curl x"), "not an allowed executable"),
    (lambda p: p["feature_coverage"][0].update(task_ids=["T7"]), "existing tasks"),
])
def test_plan_problems_are_rejected_with_the_reason(mutate, message):
    data = plan_dict()
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        S.ImplementationPlan.model_validate(data)


def test_every_approved_mvp_feature_must_be_covered():
    schema = plan_schema_for(["Track habits", "Daily reminder"])
    assert schema.__name__ == "ImplementationPlan"
    with pytest.raises(ValidationError, match="Missing: Daily reminder"):
        schema.model_validate(plan_dict())                                  # covers only "track habits"
    ok = plan_dict(feature_coverage=[{"feature": "track  habits.", "task_ids": ["T2"]},
                                     {"feature": "Daily reminder", "task_ids": ["T2"]}])
    schema.model_validate(ok)                                               # case / spacing / final dot ignored


def test_render_and_tasks():
    plan = S.ImplementationPlan.model_validate(plan_dict())
    md = render_plan_markdown(plan, "habit tracker", 0, "claude-opus-5-5")
    assert md.startswith("# Implementation plan: Habit tracker") and "claude-opus-5-5" in md
    assert "### P1. Setup" in md and "**T2. Habit tracking** · after T1" in md and "| track habits | T2 |" in md
    assert "`npm test`" in md and "listens on `$PORT`" in md
    tasks = tasks_from_plan(plan)
    assert [t["id"] for t in tasks] == ["T1", "T2"] and all(t["status"] == "pending" and t["attempts"] == 0 for t in tasks)


# --- model resolution ----------------------------------------------------------------------------------------

def test_resolve_model_never_assumes(monkeypatch):
    llm.available_models.cache_clear()
    monkeypatch.setattr(llm, "available_models", lambda: frozenset({"claude-opus-5-5", "claude-sonnet-5-5"}))
    assert llm.resolve_model("claude-opus-5-5") == ("claude-opus-5-5", "")
    model, note = llm.resolve_model("claude-opus-9")
    assert model == get_settings().anthropic_model and "not available" in note
    monkeypatch.setattr(llm, "available_models", lambda: None)
    model, note = llm.resolve_model("claude-opus-5-5")
    assert model == "claude-opus-5-5" and "unchecked" in note


# --- the graph -------------------------------------------------------------------------------------------------

def run_full(graph, thread_id: str) -> dict:
    """Start a session like the API does and drive it to the end (answers, approvals)."""
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    return finish_session(graph, config)


def to_plan_review(graph, thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    for _ in range(4):
        snapshot = graph.get_state(config)
        payload = snapshot.interrupts[0].value
        if payload["type"] == "plan_review":
            return payload
        reply = {"answers": {q: "x" for q in payload["questions"]}} if payload["type"] == "clarification" else {"action": "approve"}
        graph.invoke(Command(resume=reply), config)
    raise AssertionError("never reached the plan review")


def resume(graph, thread_id: str, **body):
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume=body), config)
    snapshot = graph.get_state(config)
    return dict(snapshot.values), snapshot


def test_planner_runs_on_the_planner_model_after_brief_approval(graph, fake_llm, fake_search):
    payload = to_plan_review(graph, "plan")
    call = next(k for k in fake_llm.kwargs if k["schema"].__name__ == "ImplementationPlan")
    settings = get_settings()
    assert call["model"] == settings.planner_model and call["effort"] == settings.planner_effort
    assert call["timeout"] == settings.planner_timeout_seconds
    assert payload["round"] == 1 and payload["changes_allowed"] is True and payload["model"] == settings.planner_model
    state, snapshot = resume(graph, "plan", action="approve")
    assert snapshot.next == () and state["status"] == "completed" and plan_is_approved(state)
    assert state["models_used"]["planner"] == settings.planner_model


def test_planner_refuses_an_unapproved_brief(graph, fake_llm, fake_search):
    state = run_full(graph, "guard")
    with pytest.raises(RuntimeError, match="approved brief"):
        planner_node(state | {"brief_markdown": state["brief_markdown"] + "edited"})     # hash no longer matches
    with pytest.raises(RuntimeError, match="approved brief"):
        planner_node(state | {"brief_approved_at": None})


def test_change_request_rewrites_the_plan_with_the_previous_one(graph, fake_llm, fake_search):
    to_plan_review(graph, "revise")
    seen = []

    def capture(system, user):
        seen.append((system, user))
        return build_plan(system, user)
    fake_llm.overrides[S.ImplementationPlan] = capture
    state, snapshot = resume(graph, "revise", action="request_changes", feedback="Use plain JavaScript, no Vite.")
    assert snapshot.next == ("await_plan_review",) and snapshot.interrupts[0].value["round"] == 2
    system, user = seen[-1]
    assert "REVISION requested by the user" in system and "<previous_plan>" in user and "no Vite" in user
    assert state["plan_revision_count"] == 1 and state["plan_review_route"] == "changes"
    assert "plan version 2" in state["plan_markdown"].lower() and not plan_is_approved(state)


def test_plan_revision_cap(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_plan_revisions", 1)
    to_plan_review(graph, "plan-cap")
    _, snapshot = resume(graph, "plan-cap", action="request_changes", feedback="Smaller tasks please.")
    payload = snapshot.interrupts[0].value
    assert payload["changes_allowed"] is False
    _, snapshot = resume(graph, "plan-cap", action="request_changes", feedback="Again.")
    assert "can only be approved" in snapshot.interrupts[0].value["error"]
    state, snapshot = resume(graph, "plan-cap", action="approve")
    assert snapshot.next == () and plan_is_approved(state)


def test_route_after_plan_review_checks_both_approvals(graph, fake_llm, fake_search):
    state = run_full(graph, "routes")
    assert G.route_after_plan_review(state) == "completion"
    assert G.route_after_plan_review(state | {"plan_markdown": "# edited"}) == "await_plan_review"
    assert G.route_after_plan_review(state | {"brief_markdown": "# edited"}) == "await_plan_review"   # brief changed
    assert G.route_after_plan_review(state | {"plan_review_route": "changes"}) == "planner"
    assert G.route_after_plan_review({}) == "await_plan_review"
    assert state["plan_approved_hash"] == plan_hash(state["plan_markdown"])


def test_approved_plan_is_saved_as_an_artifact(graph, fake_llm, fake_search, monkeypatch):
    saved = []
    monkeypatch.setattr(get_settings(), "persist_results", True)
    monkeypatch.setattr("ai_decision_arena.db.repository.save_artifact", lambda *args: saved.append(args) or len(saved))
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.save_completion", lambda *a: None)
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.remember_session", lambda *a: 0)
    state = run_full(graph, "plan-artifact")
    assert [(s[0], s[1]) for s in saved] == [("plan-artifact", "brief"), ("plan-artifact", "plan")]
    assert saved[1][2] == state["plan_markdown"] and saved[1][4] == state["plan_approved_hash"]


def test_startup_model_check_warns_when_a_model_is_missing(monkeypatch, caplog):
    from ai_decision_arena.api import main
    monkeypatch.setattr(main, "resolve_model", lambda wanted: (("claude-sonnet-5-5", f"{wanted} is not available")
                                                               if "opus" in wanted else (wanted, "")))
    with caplog.at_level("INFO", logger="ai_decision_arena.api.main"):
        main.check_models()
    assert "planner model: claude-opus-5-5 is not available" in caplog.text
    assert "implementer model claude-sonnet-5-5 is available" in caplog.text
