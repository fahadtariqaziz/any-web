"""M11 part 4: builder knowledge and skills, project-scoped memory, the trigger table, skipped-test reporting,
change tasks linked by id, the header name, and what Ask's context carries."""

import pytest

from ai_decision_arena import knowledge, memory, skills
from ai_decision_arena.chat import build_context
from ai_decision_arena.nodes.delivery import change_title, skipped_tests

from tests.test_api import client, finish_via_api, wait_until_not_running  # noqa: F401 - fixture reuse
from tests.test_delivery import reply, to_preview


def test_skipped_tests_are_read_from_the_runners_summary():
    assert skipped_tests("ℹ tests 180\nℹ pass 176\nℹ fail 0\nℹ skipped 4\nℹ todo 0") == 4
    assert skipped_tests(" Tests  176 passed | 3 skipped | 1 todo (180)") == 4
    assert skipped_tests("===== 10 passed, 2 skipped in 0.12s =====") == 2
    assert skipped_tests("# skip 3\n# todo 1") == 4
    assert skipped_tests("ℹ skipped 0") == 0 and skipped_tests("all 12 tests passed") is None


def test_a_change_task_is_named_after_the_request_and_linked_by_id(graph, fake_llm, fake_search):
    to_preview(graph, "p-change")
    long_request = "Add a percent key: 430 - 20% = 344 and 430 + 20% = 516, with tests for both cases please."
    state, _ = reply(graph, "p-change", action="change", request=long_request)
    task = state["implementation_tasks"][-1]
    assert task["id"] == "C1" and task["title"] == change_title(long_request) and task["title"].startswith("Change: Add")
    assert len(task["title"]) <= len("Change: ") + 70 and task["title"].endswith("…")
    assert state["change_requests"][-1]["task_id"] == "C1"


def test_change_turns_and_header_name_over_the_api(client, monkeypatch):  # noqa: F811
    thread_id = finish_via_api(client, "A simple calculator web app")
    r = client.post(f"/api/decisions/{thread_id}/resume",
                    json={"type": "reopen", "action": "change", "request": "Add a percent key: 430 - 20% = 344."})
    assert r.status_code == 202
    wait_until_not_running(client, thread_id)
    monkeypatch.setattr("ai_decision_arena.api.chat.list_chat_messages", lambda thread_id: [])
    change = [c for c in client.get(f"/api/chats/{thread_id}").json()["changes"] if c["action"] == "change"][-1]
    assert (change["round"], change["task_id"], change["task_status"]) == (2, "C1", "done")   # round 2, task C1
    impl = client.get(f"/api/decisions/{thread_id}/implementation").json()
    assert impl["tasks"][-1]["title"].startswith("Change: Add a percent key")


def test_the_header_shows_the_briefs_name_once_there_is_one():
    from ai_decision_arena.api.main import display_name
    assert display_name({"project_name": "simple calculator web app"}) == "simple calculator web app"
    assert display_name({"project_name": "simple calculator web app",
                         "brief": {"project_overview": {"proposed_name": "CalcPro"}}}) == "CalcPro"
    assert display_name({"project_name": "x", "brief": {"project_overview": {"proposed_name": " "}}}) == "x"


def test_old_sessions_still_link_change_tasks_by_their_old_title():
    from ai_decision_arena.api.chat import change_turns
    values = {"implementation_tasks": [{"id": "C1", "title": "Change request 3", "phase": "change", "status": "done"}],
              "change_requests": [{"round": 3, "action": "change", "request": "percent", "at": "2026-10-25T10:00:00+00:00"}]}
    (turn,) = change_turns(values)
    assert (turn.task_id, turn.task_status) == ("C1", "done")


def test_trigger_table_and_idle_preview_trigger(client):  # noqa: F811
    table = client.get("/api/triggers").json()["triggers"]
    events = {t["event"] for t in table}
    assert {"new prompt", "brief review reply", "plan review reply", "build check failed", "preview idle"} <= events
    assert all(set(t) == {"event", "condition", "action", "where"} for t in table)


def test_idle_preview_trigger_stops_previews(graph, fake_llm, fake_search, process_manager):
    from ai_decision_arena.triggers import run_idle_previews
    state, _ = to_preview(graph, "p-idle")
    assert process_manager.status("p-idle").state == "ready"
    assert run_idle_previews(process_manager, idle_minutes=0) == ["p-idle"]
    assert process_manager.status("p-idle").state == "stopped"


# --- knowledge, skills, memory --------------------------------------------------------------------------------

def test_curated_knowledge_is_builder_knowledge_with_sources():
    docs = [knowledge._parse(p) for p in sorted(knowledge.KNOWLEDGE_DIR.glob("*.md"))]
    assert len(docs) >= 5 and knowledge.INCLUDE_CURATED
    text = " ".join(d["title"] + d["content"] for d in docs).lower()
    assert not any(w in text for w in ("patient", "medication", "doctor", "symptom"))
    assert all(d["topic"] for d in docs)
    assert sum(bool(d["url"]) for d in docs) >= len(docs) - 1        # only the builder's own process doc has no URL


def test_skills_split_by_audience_and_agent_skills_match_the_stack():
    names = {s["name"]: s for s in skills.all_skills().values()}
    assert {s for s, v in names.items() if v["audience"] == "ask"} == {"write-a-change-request", "explain-build-results",
                                                                        "small-or-bigger-change"}
    picked = {s["name"] for s in skills.agent_skills_for("Vite (fast dev server) vitest: tests")}
    assert picked == {"testing-discipline", "web-ui-basics", "node-project-hygiene"}
    assert {s["name"] for s in skills.agent_skills_for("FastAPI pytest")} == {"testing-discipline", "python-project-hygiene"}
    assert "web-ui-basics" not in skills.skills_block() and "write-a-change-request" in skills.skills_block()
    assert skills.load_skill("node-project-hygiene").startswith("No skill")        # agent skills are not Ask's
    assert "<skill" in skills.load_skill("write-a-change-request")


def test_the_coding_agent_gets_the_skills_of_its_stack(graph, fake_llm, fake_search):
    to_preview(graph, "p-skills")
    prompt = fake_llm.agent.calls[0]["prompt"]
    assert "<skills>" in prompt and 'name="testing-discipline"' in prompt and 'name="web-ui-basics"' in prompt
    assert 'name="python-project-hygiene"' not in prompt


def test_project_memories_are_labelled_and_replaced_when_the_project_completes_again(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, "delete_memories", lambda user_id, **kw: calls.append(("delete", user_id, kw)) or 2)
    monkeypatch.setattr(memory, "add_memories", lambda user_id, facts, source, thread_id: calls.append(("add", facts, source)))
    state = {"user_id": "user-12345678", "project_name": "simple calculator", "project_category": "web_app",
             "project_profile": {"audience": "students"}, "constraints": {"budget": "free"}}
    assert memory.remember_session(state, "t-1") == 3
    assert calls[0] == ("delete", "user-12345678", {"thread_id": "t-1", "source": "onboarding"})
    facts = calls[1][1]
    assert all(f.startswith("[project: simple calculator]") for f in facts)
    assert "[project: simple calculator] budget (constraint): free" in facts


def test_ask_context_has_cost_limits_skills_and_measured_skips(graph, fake_llm, fake_search):
    state, _ = to_preview(graph, "p-ask")
    state["build_results"]["steps"][0]["skipped_tests"] = 3
    context = build_context(state)
    assert "<cost>" in context and '"coding_agent_left_usd"' in context
    assert "<available_skills>" in context and "write-a-change-request" in context
    assert '"skipped_tests_reported": 3' in context
