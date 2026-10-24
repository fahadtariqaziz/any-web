"""Live progress events: "what are the agents doing right now?"

Nodes call report(node, message) at each sub-step (planner done, searches done, a lane finished...).
When the graph is streamed with stream_mode "custom" (run scripts now, the FastAPI layer in Phase 8),
each event is delivered to the client immediately, while the node is still running. The events are
NOT stored in the state and do not affect the graph; they only exist for people watching.

Outside a graph run (a node called directly from a script) report() is a silent no-op.
"""

from datetime import datetime, timezone

from langgraph.config import get_stream_writer


def report(node: str, message: str, **details) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:          # "outside of a runnable context": not inside a graph run
        return
    writer({
        "type": "progress",
        "node": node,
        "message": message,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **details,
    })
