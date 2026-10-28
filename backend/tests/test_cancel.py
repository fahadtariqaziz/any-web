"""Review 2026-10-29, guardrail "safe cancellation": GraphRunner.cancel stops a run at the next step boundary; the
step in progress finishes and is checkpointed, no later step starts, the run is resumable with "continue"."""

import time
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ai_decision_arena.api.runner import GraphRunner


class S(TypedDict, total=False):
    ran: list[str]


def _wait(runner: GraphRunner, thread_id: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while runner.is_running(thread_id) and time.time() < deadline:
        time.sleep(0.02)
    assert not runner.is_running(thread_id), "the run did not stop in time"


def test_cancel_stops_after_the_current_step_and_continue_resumes_there():
    runner_box: dict = {}

    def a(state: S) -> dict:
        return {"ran": [*state.get("ran", []), "a"]}

    def b(state: S) -> dict:                         # the user presses Stop while b runs
        assert runner_box["runner"].cancel("t1")
        time.sleep(0.05)
        return {"ran": [*state.get("ran", []), "b"]}

    def c(state: S) -> dict:
        return {"ran": [*state.get("ran", []), "c"]}

    builder = StateGraph(S)
    for name, fn in (("a", a), ("b", b), ("c", c)):
        builder.add_node(name, fn)
    builder.add_edge(START, "a"); builder.add_edge("a", "b"); builder.add_edge("b", "c"); builder.add_edge("c", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    runner = runner_box["runner"] = GraphRunner(graph)
    config = {"configurable": {"thread_id": "t1"}}

    assert runner.start("t1", {"ran": []})
    _wait(runner, "t1")
    snapshot = graph.get_state(config)
    assert snapshot.values["ran"] == ["a", "b"] and snapshot.next == ("c",)     # b finished and was saved; c never ran
    assert runner.cancelled("t1") and not runner.crash("t1")
    messages = [line["message"] for line in runner.progress("t1")]
    assert any(m.startswith("stop requested") for m in messages) and any(m.startswith("stopped by you") for m in messages)

    assert runner.start("t1", None)                  # {"type": "continue"}: from the checkpoint, c only
    _wait(runner, "t1")
    assert graph.get_state(config).values["ran"] == ["a", "b", "c"] and graph.get_state(config).next == ()
    assert not runner.cancelled("t1")


def test_cancel_without_a_run_is_refused():
    runner = GraphRunner(graph=None)
    assert runner.cancel("nope") is False and not runner.cancelled("nope")
