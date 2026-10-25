"""M11 part 2: every tool call is logged with its outcome (sandbox commands, Ask tools, research searches, node
failures), targets only, and the API lists them."""

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, ToolException

from ai_decision_arena import tool_log
from ai_decision_arena.nodes.node_wrapper import wrap_node
from ai_decision_arena.research import search
from ai_decision_arena.schemas import SearchQuery
from ai_decision_arena.tools import ToolContext, run_tools
from ai_decision_arena.workspace import sandbox

from tests.test_workspace import root, ws  # noqa: F401 - fixture reuse


@pytest.fixture
def rows():
    captured: list[dict] = []
    tool_log.set_sink(captured.append)
    yield captured
    tool_log.set_sink(None)


def test_sandbox_commands_are_logged_ok_failed_and_refused(ws, rows):  # noqa: F811
    sandbox.run(ws, ["python3", "-c", "print(6 * 7)"], label="T1-verify")
    sandbox.run(ws, ["python3", "-c", "import sys; sys.exit(3)"], label="T1-verify")
    sandbox.run(ws, "curl http://example.com", label="T2")
    ok, failed, refused = rows
    assert (ok["source"], ok["tool"], ok["ok"], ok["exit_code"], ok["label"]) == ("sandbox", "python3", True, 0, "T1-verify")
    assert ok["thread_id"] == "session-a" and ok["duration_seconds"] is not None and ok["reason"] is None
    assert (failed["ok"], failed["exit_code"], failed["reason"]) == (False, 3, "exit 3")
    assert refused["ok"] is False and refused["exit_code"] is None and "curl" in refused["reason"]
    assert not any("42" in f"{r['target']} {r['reason']}" for r in rows)     # output never logged


def test_ask_tool_calls_are_logged_with_their_outcome(rows):
    def lookup(query: str) -> str:
        """Find something."""
        if query == "boom":
            raise ToolException("no index")
        return "found"

    tool = StructuredTool.from_function(lookup, handle_tool_error=True)
    message = AIMessage(content="", tool_calls=[{"name": "lookup", "args": {"query": "calculators"}, "id": "1"},
                                                {"name": "lookup", "args": {"query": "boom"}, "id": "2"},
                                                {"name": "nope", "args": {}, "id": "3"}])
    run_tools(message, [tool], ToolContext(thread_id="t-chat"))
    assert [(r["source"], r["tool"], r["ok"]) for r in rows] == [("chat", "lookup", True), ("chat", "lookup", False),
                                                                 ("chat", "nope", False)]
    assert rows[0]["target"] == "query=calculators" and "no index" in rows[1]["reason"]

    def crash(query: str) -> str:
        """Unhandled."""
        raise ValueError("bug")

    with pytest.raises(ValueError):
        run_tools(AIMessage(content="", tool_calls=[{"name": "crash", "args": {"query": "q"}, "id": "4"}]),
                  [StructuredTool.from_function(crash, handle_tool_error=True)], ToolContext(thread_id="t-chat"))
    assert (rows[-1]["tool"], rows[-1]["ok"], rows[-1]["reason"]) == ("crash", False, "ValueError: bug")


def test_research_searches_are_logged(monkeypatch, rows):
    class Client:
        def search(self, query, **kwargs):
            if query == "fails":
                raise RuntimeError("tavily down")
            return {"results": [{"url": "https://example.com/a", "title": "A", "content": "x"}]}

    monkeypatch.setattr(search, "_client", lambda: Client())
    monkeypatch.setattr(tool_log, "current_thread_id", lambda: "t-research")
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    search.search_one(SearchQuery(query="calculator apps", domain="apps", topic="existing_solutions", reason="r", preferred_domains=[]))
    with pytest.raises(RuntimeError):
        search.search_one(SearchQuery(query="fails", domain="tech", topic="libraries_and_frameworks", reason="r", preferred_domains=[]))
    assert [(r["source"], r["ok"], r["thread_id"]) for r in rows] == [("search", True, "t-research"),
                                                                       ("search", False, "t-research")]
    assert rows[0]["target"] == "apps: calculator apps" and rows[0]["label"] == "1 hits"
    assert "tavily down" in rows[1]["reason"] and "attempts" in rows[1]["reason"]


def test_a_failing_node_without_model_calls_is_still_counted():
    @wrap_node("build_check")
    def build_check(state):
        raise RuntimeError("disk full")

    entry = build_check({})["usage_log"][0]
    assert (entry["node"], entry["calls"], entry["cost_usd"], entry["error"]) == ("build_check", 0, 0.0, "unknown")


def test_logging_problems_never_break_the_caller():
    def broken(row):
        raise OSError("db gone")

    tool_log.set_sink(broken)
    try:
        tool_log.record("t", "chat", "x")                       # swallowed
    finally:
        tool_log.set_sink(None)
