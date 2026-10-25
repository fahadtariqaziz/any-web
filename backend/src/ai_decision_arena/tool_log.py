"""Tool-call log (spec §10.4 "log tool calls and their outcomes", §10.7 security events; M11 part 2).

One row in `tool_calls` per:
- agent:   a coding-agent tool call, decided by the PreToolUse hook (workspace/agent.py): allowed, or denied + reason;
- sandbox: a command run (or refused) by workspace/sandbox.run: the agent's run_command, verify commands, the build
           check; exit code, refused reasons, timed out, duration; `label` = the task / build step;
- chat:    an Ask-mode tool call (search_knowledge, web_search, remember_fact, ask_researcher), ok or error;
- search:  a Tavily search made by the research node (ok, or the error after its retries).
The per-session files stay (.builder/logs/<task>.log, commands.jsonl); this table makes them queryable across
sessions (GET /api/decisions/{id}/tool-calls, failure / refusal counters in /api/metrics).

Best effort, like usage_events: a failing write never breaks a run; nothing is written with PERSIST_RESULTS=false
unless a sink is set (tests: `set_sink(list.append)`). Targets are cut to 500 characters and never hold file contents
or command output (those can contain secrets the project wrote); only the path / command / query.
"""

from collections.abc import Callable
from datetime import datetime, timezone

MAX_TARGET = 500
SOURCES = ("agent", "sandbox", "chat", "search")

_sink: Callable[[dict], None] | None = None


def set_sink(sink: Callable[[dict], None] | None) -> None:
    """Send rows to `sink` instead of the database (tests, scripts). None = back to the database."""
    global _sink
    _sink = sink


def current_thread_id() -> str:
    """The graph run's thread id (LangGraph config; worker threads copy it), or "" outside a graph run."""
    try:
        from langgraph.config import get_config
        return (get_config().get("configurable") or {}).get("thread_id") or ""
    except RuntimeError:
        return ""


def record(thread_id: str, source: str, tool: str, *, target: str = "", ok: bool = True, reason: str | None = None,
           exit_code: int | None = None, timed_out: bool = False, duration_seconds: float | None = None,
           label: str = "") -> None:
    """Log one tool call. `reason` = why it was denied / refused / failed (None when it ran fine)."""
    row = {"thread_id": thread_id or "", "source": source, "tool": tool[:64], "target": (target or "")[:MAX_TARGET],
           "label": (label or "")[:64], "ok": ok, "reason": (reason or None) and reason[:1000], "exit_code": exit_code,
           "timed_out": timed_out, "duration_seconds": duration_seconds,
           "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}
    try:
        if _sink is not None:
            _sink(row)
            return
        from ai_decision_arena.config import get_settings
        if not get_settings().persist_results or not row["thread_id"]:
            return
        from ai_decision_arena.db.repository import save_tool_call
        save_tool_call(row)
    except Exception:                    # noqa: BLE001 - logging must never break a run
        pass
