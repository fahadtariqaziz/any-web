"""M5: the user's review of the brief (spec §6) with Claude faked: the pause, approval + hash guard, where change
requests go, the auto router, the round cap, and the approved version saved to project_artifacts."""

import pytest
from langgraph.types import Command

from ai_decision_arena import graph as G
from ai_decision_arena import schemas as S
from ai_decision_arena.brief import brief_hash, brief_is_approved
from ai_decision_arena.config import get_settings
from tests.conftest import build_brief, finish_session, tag


def to_review(graph, thread_id: str) -> dict:
    """Start a session, answer the questions, stop at the first brief review. Returns the review payload."""
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"question": "A habit tracker app for students", "mode": "full"}, config)      # like the API: no thread_id in state
    questions = graph.get_state(config).interrupts[0].value["questions"]
    graph.invoke(Command(resume={"answers": {q: "x" for q in questions}}), config)
    snapshot = graph.get_state(config)
    assert snapshot.next == ("await_brief_review",)
    return snapshot.interrupts[0].value


def reply(graph, thread_id: str, **body) -> tuple[dict, object]:
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume=body), config)
    snapshot = graph.get_state(config)
    return dict(snapshot.values), snapshot


# --- pure routing / approval -------------------------------------------------------------------------------

def test_route_after_brief_review():
    md = "# brief"
    approved = {"brief_review_route": "approved", "brief_markdown": md, "brief_approved_at": "now", "brief_approved_hash": brief_hash(md)}
    assert G.route_after_brief_review(approved) == "planner"
    assert G.route_after_brief_review(approved | {"brief_markdown": "# edited"}) == "await_brief_review"   # hash guard
    assert G.route_after_brief_review(approved | {"brief_approved_at": None}) == "await_brief_review"
    for route, node in (("wording", "brief_writer"), ("requirements", "clarification"), ("research", "research"), ("proposal", "proposer")):
        assert G.route_after_brief_review({"brief_review_route": route}) == node
    assert G.route_after_brief_review({}) == "await_brief_review"


def test_approval_matches_exactly_the_reviewed_brief(graph, fake_llm, fake_search):
    payload = to_review(graph, "approve")
    assert payload["validation_summary"]["checks_total"] > 0 and payload["wording_only"] is False
    state, snapshot = reply(graph, "approve", action="approve")
    assert snapshot.next == ("await_plan_review",) and state["status"] == "awaiting_plan_review"   # → the planner ran
    assert state["brief_approved_hash"] == brief_hash(payload["brief_markdown"]) and brief_is_approved(state)
    assert state["brief_feedback"][-1]["action"] == "approve" and state["brief_review_round_count"] == 0
    assert not brief_is_approved(state | {"brief_markdown": state["brief_markdown"] + " "})


def test_invalid_reply_is_asked_again(graph, fake_llm, fake_search):
    to_review(graph, "invalid")
    _, snapshot = reply(graph, "invalid", action="request_changes", feedback="")
    assert snapshot.next == ("await_brief_review",)
    assert "feedback is required" in snapshot.interrupts[0].value["error"]
    _, snapshot = reply(graph, "invalid", action="maybe")
    assert "Invalid reply" in snapshot.interrupts[0].value["error"]


# --- change requests ---------------------------------------------------------------------------------------

def test_wording_change_revises_the_previous_draft_and_revalidates(graph, fake_llm, fake_search):
    first = to_review(graph, "wording")
    seen = []

    def capture(system, user):
        seen.append((system, user))
        return S.BriefPartOne(**build_brief(system, user).model_dump(include=set(S.BriefPartOne.model_fields)))
    fake_llm.overrides[S.BriefPartOne] = capture
    research_before = fake_llm.count("ResearchPlan")
    state, snapshot = reply(graph, "wording", action="request_changes", feedback="Call it StudyStreak.", target="wording")

    assert snapshot.next == ("await_brief_review",)                 # revised, revalidated, shown again
    again = snapshot.interrupts[0].value
    assert again["round"] == 2 and state["brief"]["revision"] == first["brief"]["revision"] + 1
    system, user = seen[-1]
    assert "REVISION requested by the USER" in system and "<previous_draft>" in user and "Call it StudyStreak." in user
    assert fake_llm.count("FeedbackRouting") == 0 and fake_llm.count("ResearchPlan") == research_before
    assert state["brief_validation"]["verdict"] == "approve" and not state.get("brief_approved_at")


@pytest.mark.parametrize("target, first_call", [("requirements", "ClarificationResult"), ("research", "ResearchPlan"),
                                                ("proposal", "ProposerOutput")])
def test_change_requests_go_back_to_the_right_node(graph, fake_llm, fake_search, target, first_call):
    thread = f"target-{target}"
    to_review(graph, thread)
    fake_llm.calls.clear()
    plans = []
    from tests.conftest import build_research_plan

    def planner(system, user):
        plans.append(user)
        return build_research_plan(system, user)
    fake_llm.overrides[S.ResearchPlan] = planner
    state, snapshot = reply(graph, thread, action="request_changes", feedback="It must also work on phones.", target=target)

    assert snapshot.next == ("await_brief_review",)
    assert fake_llm.calls[0][0] == first_call                       # the first agent that ran after the router
    assert state["brief_review_route"] == target and state["brief_feedback"][-1]["resolved_target"] == target
    assert len(plans) == (0 if target == "proposal" else 1)          # proposal changes reuse the research
    if plans:                                                       # the feedback is the follow-up search's focus
        assert "work on phones" in tag("focus", plans[0])


def test_feedback_reaches_every_agent_as_user_input(graph, fake_llm, fake_search):
    to_review(graph, "reaches")
    prompts = []

    def proposer(system, user):
        prompts.append(user)
        from tests.conftest import build_proposer
        return build_proposer(system, user)
    fake_llm.overrides[S.ProposerOutput] = proposer
    reply(graph, "reaches", action="request_changes", feedback="Prefer a native mobile app.", target="proposal")
    assert '<request round="1" about="proposal">Prefer a native mobile app.</request>' in prompts[-1]


def test_auto_target_is_decided_by_the_router_llm(graph, fake_llm, fake_search):
    to_review(graph, "auto")
    fake_llm.overrides[S.FeedbackRouting] = lambda s, u: S.FeedbackRouting(reasoning="new fact source", target="research")
    state, _ = reply(graph, "auto", action="request_changes", feedback="Check the app store reviews again.")
    assert fake_llm.count("FeedbackRouting") == 1
    assert state["brief_feedback"][-1]["target"] == "auto" and state["brief_feedback"][-1]["resolved_target"] == "research"
    assert state["brief_review_route"] == "research"


def test_round_cap_accepts_only_wording(graph, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_review_rounds", 1)
    to_review(graph, "cap")
    _, snapshot = reply(graph, "cap", action="request_changes", feedback="Shorter please.", target="wording")
    payload = snapshot.interrupts[0].value
    assert payload["wording_only"] is True and payload["round"] == 2
    _, snapshot = reply(graph, "cap", action="request_changes", feedback="Research more.", target="research")
    assert "only wording changes" in snapshot.interrupts[0].value["error"]
    routed_before = fake_llm.count("FeedbackRouting")
    state, snapshot = reply(graph, "cap", action="request_changes", feedback="Even shorter.", target="auto")
    assert fake_llm.count("FeedbackRouting") == routed_before          # auto became wording without an LLM call
    assert state["brief_feedback"][-1]["target"] == "wording" and snapshot.next == ("await_brief_review",)
    state, snapshot = reply(graph, "cap", action="approve")
    assert snapshot.next == ("await_plan_review",) and state["brief_review_round_count"] == 2


def test_approved_brief_is_saved_as_an_artifact(graph, fake_llm, fake_search, monkeypatch):
    saved = []
    monkeypatch.setattr(get_settings(), "persist_results", True)
    monkeypatch.setattr("ai_decision_arena.db.repository.save_artifact", lambda *args: saved.append(args) or 1)
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.save_completion", lambda *a: None)
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.remember_session", lambda *a: 0)
    payload = to_review(graph, "artifact")
    state, _ = reply(graph, "artifact", action="approve")
    assert len(saved) == 1
    thread_id, kind, markdown, content, digest, approved_at = saved[0]
    assert (thread_id, kind) == ("artifact", "brief") and markdown == payload["brief_markdown"]
    assert digest == state["brief_approved_hash"] and approved_at == state["brief_approved_at"]


def test_failed_artifact_save_does_not_fail_the_session(graph, fake_llm, fake_search, monkeypatch):
    def broken(*args):
        raise RuntimeError("db down")
    monkeypatch.setattr(get_settings(), "persist_results", True)
    monkeypatch.setattr("ai_decision_arena.db.repository.save_artifact", broken)
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.save_completion", lambda *a: None)
    monkeypatch.setattr("ai_decision_arena.nodes.final_report.remember_session", lambda *a: 0)
    to_review(graph, "artifact-broken")
    state = finish_session(graph, {"configurable": {"thread_id": "artifact-broken"}})
    assert state["status"] == "completed" and brief_is_approved(state)
