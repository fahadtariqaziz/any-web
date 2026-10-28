"""The HTTP layer on top of a faked graph: start, poll, pause, resume, report; the error shape."""

import time
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from ai_decision_arena.api.main import app
from ai_decision_arena.api.runner import GraphRunner
from ai_decision_arena.graph import build_graph


@asynccontextmanager
async def memory_lifespan(application):
    """Same wiring as api.main.lifespan, but InMemorySaver instead of Postgres and no scheduler."""
    graph = build_graph(checkpointer=InMemorySaver())
    application.state.graph = graph
    application.state.runner = GraphRunner(graph)
    yield


@pytest.fixture
def client(fake_llm, fake_search):
    app.router.lifespan_context = memory_lifespan
    with TestClient(app) as c:
        yield c


def wait_until_not_running(client: TestClient, thread_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/decisions/{thread_id}").json()
        if status["run_state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("run did not stop in time")


def test_unknown_session_is_404_with_error_shape(client):
    r = client.get("/api/decisions/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "No session with thread_id does-not-exist."}}


def test_invalid_body_is_422_in_our_error_shape(client):
    r = client.post("/api/decisions", json={"question": "ab"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_input"
    assert "question" in r.json()["error"]["message"]


def test_start_pause_resume_report(client):
    started = client.post("/api/decisions", json={"question": "A habit tracker app for students"})
    assert started.status_code == 202
    thread_id = started.json()["thread_id"]

    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "paused"
    assert status["workflow_status"] == "awaiting_clarification"
    assert status["pending"]["type"] == "clarification"
    assert status["counters"]["clarification_rounds"] == 0
    assert status["next_nodes"] == ["await_clarification"]
    payload = status["pending"]["payload"]
    assert payload["max_rounds"] == 1 and set(payload["options"]) == set(payload["questions"])    # 2026-10-29
    assert payload["options"]["Who are the main users of this app?"] == ["Students", "Small business owners", "My own team"]
    questions = status["pending"]["payload"]["questions"]

    # not finished yet → 409
    assert client.get(f"/api/decisions/{thread_id}/report").status_code == 409
    no_brief = client.get(f"/api/decisions/{thread_id}/brief")
    assert no_brief.status_code == 409 and no_brief.json()["error"]["code"] == "no_brief"
    # wrong pause type → 409
    wrong = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "continue"})
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "not_interrupted"
    # answers to questions that were not asked → 422
    bad = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {"nope?": "x"}})
    assert bad.status_code == 422

    ok = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {questions[0]: "2 years"}})
    assert ok.status_code == 202
    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "paused" and status["pending"]["type"] == "brief_review"
    assert status["has_brief"] is True                         # the validated brief is readable during the review
    assert client.get(f"/api/decisions/{thread_id}/brief").json()["approved_at"] is None
    # wrong pause type → 409; changes without feedback → 422
    wrong = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {}})
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "wrong_pause_type"
    empty = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "brief_review", "action": "request_changes", "feedback": " "})
    assert empty.status_code == 422
    bad_target = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "brief_review", "action": "approve", "target": "nowhere"})
    assert bad_target.status_code == 422

    approve = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "brief_review", "action": "approve"})
    assert approve.status_code == 202
    status = wait_until_not_running(client, thread_id)
    assert status["pending"]["type"] == "plan_review" and status["has_plan"] is True
    plan = client.get(f"/api/decisions/{thread_id}/plan").json()
    assert plan["approved_at"] is None and plan["markdown"].startswith("# Implementation plan") and plan["tasks"]
    no_feedback = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "plan_review", "action": "request_changes"})
    assert no_feedback.status_code == 422
    assert client.post(f"/api/decisions/{thread_id}/resume", json={"type": "plan_review", "action": "approve"}).status_code == 202
    status = wait_until_not_running(client, thread_id)
    assert client.get(f"/api/decisions/{thread_id}/plan").json()["approved_at"]

    # built (fake agent, real verify), build check passed, preview running → paused for change requests
    assert status["run_state"] == "paused" and status["pending"]["type"] == "change_request"
    assert status["has_build"] is True
    impl = client.get(f"/api/decisions/{thread_id}/implementation").json()
    assert [t["status"] for t in impl["tasks"]] == ["done", "done"] and impl["build"]["passed"] and impl["cost_usd"] > 0
    preview = client.get(f"/api/decisions/{thread_id}/preview").json()
    assert preview["state"] == "ready" and preview["url"].startswith("http://localhost:")
    assert httpx.get(preview["url"], timeout=5).status_code == 200                      # the real dev server
    assert client.post(f"/api/decisions/{thread_id}/resume",
                       json={"type": "change_request", "action": "change"}).status_code == 422   # no request text
    assert client.post(f"/api/decisions/{thread_id}/resume", json={"type": "plan_review", "action": "approve"}).status_code == 409
    restarted = client.post(f"/api/decisions/{thread_id}/preview/restart").json()
    assert restarted["state"] == "ready" and restarted["port"]
    # app settings (.env.example): names + steps out, values in, a value is never returned
    from ai_decision_arena.workspace.paths import workspace_for
    ws = workspace_for(thread_id)
    (ws.app / ".env.example").write_text("# Project URL from Supabase → Project Settings → API\nVITE_SUPABASE_URL=\n")
    settings = client.get(f"/api/decisions/{thread_id}/app-settings").json()
    assert settings["missing"] == ["VITE_SUPABASE_URL"] and settings["guides"][0]["service"] == "Supabase"
    assert settings["variables"][0]["help"] == ["Project URL from Supabase → Project Settings → API"]
    assert client.put(f"/api/decisions/{thread_id}/app-settings", json={"values": {"PATH": "/x"}}).status_code == 422
    saved = client.put(f"/api/decisions/{thread_id}/app-settings",
                       json={"values": {"VITE_SUPABASE_URL": "https://abc.supabase.co"}})
    assert saved.status_code == 200 and "abc.supabase.co" not in saved.text
    assert saved.json()["missing"] == [] and saved.json()["preview"]["state"] == "ready"   # restarted with it
    assert "abc.supabase.co" not in (ws.app / ".env.example").read_text() and not (ws.app / ".env").exists()
    assert client.post(f"/api/decisions/{thread_id}/resume",
                       json={"type": "change_request", "action": "finish"}).status_code == 202
    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "finished"
    assert status["workflow_status"] == "completed"
    assert status["has_report"] is True
    assert status["error"] is None
    assert status["counters"]["evidence"] > 0 and status["counters"]["proposals"] > 0

    report = client.get(f"/api/decisions/{thread_id}/report")
    assert report.status_code == 200
    body = report.json()["report"]
    assert body["winner"]["proposal"]["proposal_id"] == "proposal_a"
    assert [a["proposal"]["proposal_id"] for a in body["alternatives"]] == ["proposal_b"]

    assert status["has_brief"] is True
    brief = client.get(f"/api/decisions/{thread_id}/brief")
    assert brief.status_code == 200
    brief = brief.json()
    assert brief["validation"]["verdict"] == "approve" and brief["approved_at"]
    assert brief["markdown"].startswith("# ") and "## 10. References" in brief["markdown"]
    known_urls = {e["source_url"] for e in client.get(f"/api/decisions/{thread_id}/evidence").json()["evidence"]}
    assert brief["brief"]["references"] and {r["url"] for r in brief["brief"]["references"]} <= known_urls

    evidence = client.get(f"/api/decisions/{thread_id}/evidence").json()
    assert evidence["count"] == status["counters"]["evidence"]
    live = client.get(f"/api/decisions/{thread_id}/live").json()
    assert live["run_state"] == "finished" and live["debate"]["verdict"]["decision"] == "proceed"
    assert live["case"]["clarification_answers"][questions[0]] == "2 years"


def test_second_start_while_running_is_409(client):
    started = client.post("/api/decisions", json={"question": "A habit tracker app for students"}).json()
    thread_id = started["thread_id"]
    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "paused"
    questions = status["pending"]["payload"]["questions"]
    first = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {}})
    assert first.status_code == 202
    second = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {questions[0]: "x"}})
    assert second.status_code == 409 and second.json()["error"]["code"] == "already_running"
    wait_until_not_running(client, thread_id)


def test_cancel_needs_a_running_session(client):
    """Review 2026-10-29: POST /cancel is the safe stop; 409 when nothing runs, 404 for an unknown session."""
    started = client.post("/api/decisions", json={"question": "A habit tracker app for students"}).json()
    status = wait_until_not_running(client, started["thread_id"])
    assert status["run_state"] == "paused" and status["cancelled"] is False
    r = client.post(f"/api/decisions/{started['thread_id']}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_running"
    assert client.post("/api/decisions/does-not-exist/cancel").status_code == 404


def test_brief_change_request_round_trip_and_wording_only_cap(client, monkeypatch):
    from ai_decision_arena.config import get_settings
    monkeypatch.setattr(get_settings(), "max_review_rounds", 1)
    thread_id = client.post("/api/decisions", json={"question": "A habit tracker app for students"}).json()["thread_id"]
    status = wait_until_not_running(client, thread_id)
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {}})
    status = wait_until_not_running(client, thread_id)
    assert status["pending"]["payload"]["round"] == 1

    r = client.post(f"/api/decisions/{thread_id}/resume",
                    json={"type": "brief_review", "action": "request_changes", "feedback": "Shorter, please.", "target": "wording"})
    assert r.status_code == 202
    status = wait_until_not_running(client, thread_id)
    payload = status["pending"]["payload"]
    assert status["pending"]["type"] == "brief_review" and payload["round"] == 2 and payload["wording_only"] is True
    assert client.get(f"/api/decisions/{thread_id}/brief").json()["review_round"] == 1

    capped = client.post(f"/api/decisions/{thread_id}/resume",
                         json={"type": "brief_review", "action": "request_changes", "feedback": "More research.", "target": "research"})
    assert capped.status_code == 422 and "only wording" in capped.json()["error"]["message"]
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "brief_review", "action": "approve"})
    assert wait_until_not_running(client, thread_id)["pending"]["type"] == "plan_review"
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "plan_review", "action": "approve"})
    assert wait_until_not_running(client, thread_id)["pending"]["type"] == "change_request"
    client.post(f"/api/decisions/{thread_id}/resume",
                json={"type": "change_request", "action": "change", "request": "Add a footer."})
    assert wait_until_not_running(client, thread_id)["pending"]["type"] == "change_request"
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "change_request", "action": "finish"})
    assert wait_until_not_running(client, thread_id)["workflow_status"] == "completed"

    # M10: the builder chat's transcript carries the whole conversation, in order, with the change's task
    monkeypatch.setattr("ai_decision_arena.api.chat.list_chat_messages", lambda thread_id: [])   # no DB in tests
    chat = client.get(f"/api/chats/{thread_id}").json()
    assert chat["ready"] is True and chat["question"] == "A habit tracker app for students"
    assert [(r["kind"], r["action"]) for r in chat["reviews"]] == [
        ("brief", "request_changes"), ("brief", "approve"), ("plan", "approve")]
    assert chat["reviews"][0]["feedback"] == "Shorter, please." and chat["reviews"][0]["target"] == "wording"
    assert [(c["action"], c["task_id"], c["task_status"]) for c in chat["changes"]] == [
        ("change", "C1", "done"), ("finish", None, None)]
    assert chat["changes"][0]["request"] == "Add a footer."

    # Ask mode sees the brief, the plan, the build and the user's requests (measured facts only)
    from ai_decision_arena.api.runner import graph_config
    from ai_decision_arena.chat import build_context
    context = build_context(app.state.graph.get_state(graph_config(thread_id)).values)
    assert '<brief approved="true"># ' in context and '"approved": true' in context
    assert '"id": "C1"' in context and '"passed": true' in context and "Add a footer." in context
    assert "Shorter, please." in context and "<current_stage>completed</current_stage>" in context


def test_ask_mode_waits_for_the_report(client):
    thread_id = client.post("/api/decisions", json={"question": "A simple calculator web app"}).json()["thread_id"]
    wait_until_not_running(client, thread_id)                       # paused at the questions: no report yet
    chat = client.get(f"/api/chats/{thread_id}").json()
    assert chat["ready"] is False and chat["reviews"] == [] and chat["changes"] == [] and chat["messages"] == []
    r = client.post(f"/api/chats/{thread_id}/messages", json={"content": "Why this stack?"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "onboarding_not_finished"


def finish_via_api(client, question: str) -> str:
    thread_id = client.post("/api/decisions", json={"question": question}).json()["thread_id"]
    for reply in ({"type": "clarification", "answers": {}}, {"type": "brief_review", "action": "approve"},
                  {"type": "plan_review", "action": "approve"}, {"type": "change_request", "action": "finish"}):
        assert wait_until_not_running(client, thread_id)["pending"]["type"] == reply["type"]
        assert client.post(f"/api/decisions/{thread_id}/resume", json=reply).status_code == 202
    return thread_id


def test_reopen_a_finished_project_for_another_change(client, monkeypatch):
    thread_id = finish_via_api(client, "A simple calculator web app")
    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "finished" and status["reopen_actions"] == ["change", "replan"]

    too_short = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "reopen", "action": "change", "request": "x"})
    assert too_short.status_code == 422
    r = client.post(f"/api/decisions/{thread_id}/resume",
                    json={"type": "reopen", "action": "change", "request": "Add a percent key: 430 - 20% = 344."})
    assert r.status_code == 202
    status = wait_until_not_running(client, thread_id)
    # the same path as an answered pause: task C1 → build check → preview restarted → paused again
    assert status["run_state"] == "paused" and status["pending"]["type"] == "change_request"
    assert status["reopen_actions"] == []
    assert client.post(f"/api/decisions/{thread_id}/resume",
                       json={"type": "reopen", "action": "change", "request": "Another one"}).status_code == 409
    impl = client.get(f"/api/decisions/{thread_id}/implementation").json()
    assert impl["tasks"][-1]["id"] == "C1" and impl["tasks"][-1]["status"] == "done" and impl["build"]["passed"]
    assert client.get(f"/api/decisions/{thread_id}/preview").json()["state"] == "ready"

    # "Download code": the built files, as JSON for the folder writer and as a zip
    code = client.get(f"/api/decisions/{thread_id}/code").json()
    assert code["folder_name"]
    assert {f["path"] for f in code["files"]} >= {"package.json", "src/main.js", "src/habits.js"}   # the fake plan's files
    zipped = client.get(f"/api/decisions/{thread_id}/code.zip")
    assert zipped.status_code == 200 and zipped.headers["content-type"] == "application/zip"
    assert zipped.headers["content-disposition"] == f'attachment; filename="{code['folder_name']}.zip"'

    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "change_request", "action": "finish"})
    status = wait_until_not_running(client, thread_id)
    assert status["run_state"] == "finished" and status["workflow_status"] == "completed"
    monkeypatch.setattr("ai_decision_arena.api.chat.list_chat_messages", lambda thread_id: [])
    changes = client.get(f"/api/chats/{thread_id}").json()["changes"]
    assert [(c["action"], c["task_id"], c["task_status"]) for c in changes] == [
        ("finish", None, None), ("change", "C1", "done"), ("finish", None, None)]

    # a reopened bigger change updates the brief first (brief review), then a plan with only the new work
    r = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "reopen", "action": "replan", "request": "Use a scientific layout."})
    assert r.status_code == 202
    status = wait_until_not_running(client, thread_id)
    assert status["pending"]["type"] == "brief_review"
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "brief_review", "action": "approve"})
    status = wait_until_not_running(client, thread_id)
    assert status["pending"]["type"] == "plan_review" and status["pending"]["payload"]["new_task_count"] == 1
    chat = client.get(f"/api/chats/{thread_id}").json()
    assert chat["changes"][-1]["action"] == "replan"                        # shown once: as a change turn
    # (review times have 1 s resolution: this fast test may give two replies the same second, so count, don't order)
    assert sum(r["kind"] == "brief" and r["action"] == "approve" for r in chat["reviews"]) == 2


def test_reopen_respects_the_change_limit_and_needs_a_finished_build(client, monkeypatch):
    from ai_decision_arena.config import get_settings
    thread_id = finish_via_api(client, "A habit tracker app for students")
    wait_until_not_running(client, thread_id)
    monkeypatch.setattr(get_settings(), "max_change_requests", 0)
    assert client.get(f"/api/decisions/{thread_id}").json()["reopen_actions"] == []
    r = client.post(f"/api/decisions/{thread_id}/resume", json={"type": "reopen", "action": "change", "request": "More."})
    assert r.status_code == 422 and "maximum" in r.json()["error"]["message"]

    paused = client.post("/api/decisions", json={"question": "A simple calculator web app"}).json()["thread_id"]
    wait_until_not_running(client, paused)                  # waiting for answers: not finished
    r = client.post(f"/api/decisions/{paused}/resume", json={"type": "reopen", "action": "change", "request": "More."})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_finished"
    assert client.get(f"/api/decisions/{paused}/code").json()["error"]["code"] == "no_implementation"   # nothing built


def test_draft_brief_is_readable_while_the_validator_checks_it(client):
    thread_id = client.post("/api/decisions", json={"question": "A habit tracker app for students"}).json()["thread_id"]
    status = wait_until_not_running(client, thread_id)
    questions = status["pending"]["payload"]["questions"]
    client.post(f"/api/decisions/{thread_id}/resume", json={"type": "clarification", "answers": {questions[0]: "2 years"}})
    wait_until_not_running(client, thread_id)
    # Rewind to "the writer finished, the validator is running": a fresh draft without a validation of it.
    graph, config = app.state.graph, {"configurable": {"thread_id": thread_id}}
    graph.update_state(config, {"status": "validating_brief", "brief_validation": {}})
    status = client.get(f"/api/decisions/{thread_id}").json()
    assert status["has_brief"] is False and status["has_draft_brief"] is True
    draft = client.get(f"/api/decisions/{thread_id}/brief").json()
    assert draft["is_draft"] is True and draft["validation"] is None and draft["markdown"].startswith("# ")
