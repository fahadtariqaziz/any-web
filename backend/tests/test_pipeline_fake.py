"""The whole graph end to end on an InMemorySaver, with Claude and Tavily faked: pause, resume, report."""

from langgraph.types import Command

from ai_decision_arena import schemas as S
from tests.conftest import finish_session

CONFIG = {"configurable": {"thread_id": "pipeline-test"}}


def test_full_pipeline_pauses_for_clarification_then_completes(graph, fake_llm, fake_search):
    result = graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, CONFIG)
    snapshot = graph.get_state(CONFIG)

    # 1) paused at the clarification question, nothing researched yet
    assert snapshot.next == ("await_clarification",)
    payload = snapshot.interrupts[0].value
    assert payload["type"] == "clarification" and payload["round"] == 1
    assert len(payload["questions"]) == 2
    assert result["status"] == "awaiting_clarification"
    assert fake_llm.count("ResearchPlan") == 0

    # 2) answer → research → debate → verification → report → brief → paused for the user's review
    answers = {q: "about 2 years" for q in payload["questions"]}
    result = graph.invoke(Command(resume={"answers": answers}), CONFIG)
    snapshot = graph.get_state(CONFIG)
    assert snapshot.next == ("await_brief_review",)
    review = snapshot.interrupts[0].value
    assert review["type"] == "brief_review" and review["round"] == 1 and review["brief_markdown"].startswith("# ")
    assert result["status"] == "awaiting_brief_review" and not result.get("brief_approved_at")

    # 3) approve the brief → the planner writes the plan → paused for the plan review
    result = graph.invoke(Command(resume={"action": "approve"}), CONFIG)
    snapshot = graph.get_state(CONFIG)
    assert snapshot.next == ("await_plan_review",)
    assert result["brief_approved_at"] and result["brief_review_route"] == "approved"
    assert snapshot.interrupts[0].value["type"] == "plan_review" and result["status"] == "awaiting_plan_review"

    # 4) approve the plan → implementer (fake agent, real sandbox verify) → build check → preview (a real server)
    result = graph.invoke(Command(resume={"action": "approve"}), CONFIG)
    snapshot = graph.get_state(CONFIG)
    assert snapshot.next == ("await_change_request",) and result["status"] == "previewing"
    assert result["plan_approved_at"] and [t["status"] for t in result["implementation_tasks"]] == ["done", "done"]
    assert result["build_results"]["passed"] and result["preview"]["state"] == "ready"
    assert snapshot.interrupts[0].value["preview"]["url"].startswith("http://localhost:")

    # 5) finish → completion
    result = graph.invoke(Command(resume={"action": "finish"}), CONFIG)
    assert graph.get_state(CONFIG).next == ()
    assert result["workspace_dir"] and result["metrics"]["tasks"]["done"] == 2 and result["metrics"]["build_passed"]
    assert result["status"] == "completed"
    assert result["clarification_round_count"] == 1
    assert result["clarification_answers"] == answers
    assert result["project_profile"]["audience"] == "university students"

    # research: evidence ids are Python-assigned and URLs come from the (fake) search hits, never from the LLM
    assert result["evidence"], "no evidence extracted"
    assert [e["evidence_id"] for e in result["evidence"]] == [f"ev_{i:03d}" for i in range(1, len(result["evidence"]) + 1)]
    assert all(e["source_url"].startswith("https://example.org/") for e in result["evidence"])
    assert {e["domain"] for e in result["evidence"]} == {"apps", "papers", "tech"}

    # debate: 2 proposals, one critique each, one winner, verdict proceed
    assert [p["proposal_id"] for p in result["proposals"]] == ["proposal_a", "proposal_b"]
    assert [c["proposal_id"] for c in result["criticisms"]] == ["proposal_a", "proposal_b"]
    assert result["verdict"]["winning_proposal_id"] == "proposal_a"
    assert result["verdict"]["decision"] == "proceed"
    assert result["debate_round"] == 1

    # verification + report
    assert result["checker_verdict"]["decision"] == "proceed"
    assert all(v["proposal_id"] == "proposal_a" for v in result["verification_results"])
    report = result["final_report"]
    assert report["winner"]["proposal"]["proposal_id"] == "proposal_a" and report["winner"]["is_winner"] is True
    assert [a["proposal"]["proposal_id"] for a in report["alternatives"]] == ["proposal_b"]
    assert report["winner"]["key_evidence"][0]["url"].startswith("https://example.org/")
    assert report["is_conditional"] is False
    assert result["metrics"]["evidence_count"] == len(result["evidence"])
    assert "onboarding_summary" not in result


def test_quick_mode_runs_every_node_with_one_proposal(graph, fake_llm, fake_search):
    config = {"configurable": {"thread_id": "quick-test"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "quick"}, config)
    result = finish_session(graph, config, answer="")
    assert result["status"] == "completed"
    assert len(result["proposals"]) == 1
    assert fake_llm.count("Criticism") == 1               # critic and checker run in quick mode too
    assert fake_llm.count("ProposalVerification") == 1
    assert result["final_report"]["winner"]["proposal"]["proposal_id"] == "proposal_a"
    assert all(v == "(skipped by user)" for v in result["clarification_answers"].values())


def test_judge_can_send_the_graph_back_to_research_once(graph, fake_llm, fake_search):
    from tests.conftest import build_judgement
    calls = {"n": 0}

    def insufficient_first(system, user):
        calls["n"] += 1
        j = build_judgement(system, user)
        if calls["n"] == 1:
            return j.model_copy(update={"evidence_sufficient": False, "insufficiency_reason": "thin", "required_evidence": ["pricing"]})
        return j
    fake_llm.overrides[S.ProposalJudgement] = insufficient_first
    config = {"configurable": {"thread_id": "loop-test"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    result = finish_session(graph, config)
    assert result["status"] == "completed"
    assert result["research_retry_count"] == 1 and result["debate_round"] == 2
    assert fake_llm.count("ResearchPlan") == 2 and fake_llm.count("ProposerOutput") == 2
    assert result["verdict"]["decision"] == "proceed"


def test_a_failing_node_ends_the_session_as_failed(graph, fake_llm, fake_search):
    def boom(system, user):
        raise RuntimeError("simulated bug")
    fake_llm.overrides[S.ProposerOutput] = boom
    config = {"configurable": {"thread_id": "fail-test"}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)
    questions = graph.get_state(config).interrupts[0].value["questions"]
    result = graph.invoke(Command(resume={"answers": {q: "x" for q in questions}}), config)
    assert result["status"] == "failed"
    assert result["error"]["node"] == "proposer"
    assert result["error"]["category"] == "unknown"
    assert "simulated bug" in result["error"]["message"]
    assert "final_report" not in result
