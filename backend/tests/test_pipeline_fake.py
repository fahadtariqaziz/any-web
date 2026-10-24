"""The whole graph end to end on an InMemorySaver, with Claude and Tavily faked: pause, resume, report."""

from langgraph.types import Command

CONFIG = {"configurable": {"thread_id": "pipeline-test"}}


def test_full_pipeline_pauses_for_clarification_then_completes(graph, fake_llm, fake_search):
    result = graph.invoke({"question": "I have diabetes", "mode": "full"}, CONFIG)
    snapshot = graph.get_state(CONFIG)

    # 1) paused at the clarification question, nothing researched yet
    assert snapshot.next == ("await_clarification",)
    payload = snapshot.interrupts[0].value
    assert payload["type"] == "clarification" and payload["round"] == 1
    assert len(payload["questions"]) == 2
    assert result["status"] == "awaiting_clarification"
    assert fake_llm.count("ResearchPlan") == 0

    # 2) answer → research → debate → verification → report → completion
    answers = {q: "about 2 years" for q in payload["questions"]}
    result = graph.invoke(Command(resume={"answers": answers}), CONFIG)
    assert graph.get_state(CONFIG).next == ()
    assert result["status"] == "completed"
    assert result["clarification_round_count"] == 1
    assert result["clarification_answers"] == answers
    assert result["health_profile"]["diagnosed_since"] == "2 years"

    # research: evidence ids are Python-assigned and URLs come from the (fake) search hits, never from the LLM
    assert result["evidence"], "no evidence extracted"
    assert [e["evidence_id"] for e in result["evidence"]] == [f"ev_{i:03d}" for i in range(1, len(result["evidence"]) + 1)]
    assert all(e["source_url"].startswith("https://example.org/") for e in result["evidence"])
    assert {e["perspective"] for e in result["evidence"]} == {"research", "doctor", "patient"}

    # debate: one winner per lane, scores computed, verdict proceed
    assert set(result["verdict"]["winning_plan_ids"]) == {"research", "doctor", "patient"}
    assert result["verdict"]["decision"] == "proceed"
    assert result["debate_round"] == 1

    # verification + report
    assert result["checker_verdict"]["decision"] == "proceed"
    report = result["final_report"]
    assert [p["perspective"] for p in report["perspectives"]] == ["research", "doctor", "patient"]
    assert all(p["plan"] for p in report["perspectives"])
    assert report["is_conditional"] is False
    assert result["metrics"]["evidence_count"] == len(result["evidence"])
    assert "onboarding_summary" not in result                 # full mode: no chat summary


def test_quick_mode_skips_critic_and_checker(graph, fake_llm, fake_search):
    config = {"configurable": {"thread_id": "quick-test"}}
    graph.invoke({"question": "I have diabetes", "mode": "quick"}, config)
    questions = graph.get_state(config).interrupts[0].value["questions"]
    result = graph.invoke(Command(resume={"answers": {q: "" for q in questions}}), config)
    assert result["status"] == "completed"
    assert fake_llm.count("CriticOutput") == 0
    assert fake_llm.count("PlanVerification") == 0
    assert result["onboarding_summary"]["opening"]
    assert all(v == "(skipped by user)" for v in result["clarification_answers"].values())


def test_a_failing_node_ends_the_session_as_failed(graph, fake_llm, fake_search, monkeypatch):
    def boom(system, user):
        raise RuntimeError("simulated bug")
    from ai_decision_arena import schemas as S
    fake_llm.overrides[S.ProposerOutput] = boom
    config = {"configurable": {"thread_id": "fail-test"}}
    graph.invoke({"question": "I have diabetes", "mode": "full"}, config)
    questions = graph.get_state(config).interrupts[0].value["questions"]
    result = graph.invoke(Command(resume={"answers": {q: "x" for q in questions}}), config)
    assert result["status"] == "failed"
    assert result["error"]["node"] == "proposer"
    assert result["error"]["category"] == "unknown"
    assert "simulated bug" in result["error"]["message"]
    assert "final_report" not in result
