"""The wrapper around every graph node: session mode, active time, and turning a failure into state.

- Runs the node inside `session_mode(state["mode"])`, so a quick (patient chat) session gets the quick
  settings everywhere (config.py).
- Accumulates `active_seconds` (time inside nodes, human pauses excluded), which the session time budget uses.
- If the node raises, the graph does NOT crash: the error is stored as a safe ErrorRecord in `error`
  with status "failed", and the guarded edges in graph.py send the graph to completion, which saves the
  session as failed. The API shows `error.message` to the user. There is no node-level retry: retries
  happen inside the LLM call (SDK retries, self-correction, fallback model; see llm.py).
- LangGraph's own interrupt exceptions are re-raised untouched (they are control flow, not failures).

Never put API keys or request payloads in ErrorRecord.message: str(exc) of the SDKs we use does not
contain them, and the message is cut at 500 characters.
"""

import functools
import time

from langgraph.errors import GraphBubbleUp

from ai_decision_arena.config import session_mode
from ai_decision_arena.llm import LLMUnavailableError
from ai_decision_arena.nodes.intake import InvalidInputError
from ai_decision_arena.progress import report
from ai_decision_arena.schemas import ErrorRecord
from ai_decision_arena.state import ArenaState


def classify(exc: Exception) -> str:
    """The error category the API sends as `error.code` (the patient chat treats invalid_input specially)."""
    if isinstance(exc, InvalidInputError):
        return "invalid_input"
    if isinstance(exc, LLMUnavailableError):
        return "llm_unavailable"
    return "unknown"                                 # most likely a bug in our code


def wrap_node(name: str):
    """Decorator: run the node in its session mode, measure active time, turn an exception into a failed state."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(state: ArenaState) -> dict:
            started = time.time()
            try:
                with session_mode(state.get("mode")):
                    update = dict(fn(state) or {})
            except GraphBubbleUp:                    # interrupt(): control flow, must bubble up
                raise
            except Exception as exc:                 # noqa: BLE001 - this is the failure boundary
                category = classify(exc)
                message = str(exc) if category != "unknown" else f"{type(exc).__name__}: {exc}"
                record = ErrorRecord(node=name, operation=type(exc).__name__, category=category, message=message[:500])
                report(name, f"failed: {message[:200]}")
                return {
                    "error": record.model_dump(mode="json"),
                    "status": "failed",
                    "current_node": name,
                    "active_seconds": round(state.get("active_seconds", 0.0) + time.time() - started, 3),
                }
            update["active_seconds"] = round(state.get("active_seconds", 0.0) + time.time() - started, 3)
            return update
        return wrapped
    return decorate
