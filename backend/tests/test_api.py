"""The HTTP layer on top of a faked graph: start, poll, pause, resume, report; the error shape."""

import time
from contextlib import asynccontextmanager

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
    assert brief["validation"]["verdict"] == "approve"
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
