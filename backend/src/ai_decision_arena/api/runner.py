"""Runs the graph in background threads, so HTTP requests return immediately.

A full run takes 3-4 minutes; an HTTP request should not hang that long. So POST starts a run here
and returns 202, and the client polls GET for progress. Rules:
- at most ONE run per session at a time (`start` refuses a second one → the API answers 409),
- progress lines (the same "·" messages the CLI prints) are kept in memory, per session,
- the session row in decision_sessions gets the current status at the start and at every pause.

The truth about a session lives in the CHECKPOINT (graph.get_state), not here: if the server restarts,
this in-memory bookkeeping is gone but the session can still be read and continued.

Threads are daemon threads: stopping the server does not wait minutes for a run to finish. The run
just stops after its last saved step, and the session shows up as "interrupted".
"""

import logging
import threading
import time
from datetime import datetime, timezone

from ai_decision_arena.config import get_settings
from ai_decision_arena.db.repository import save_session_status

log = logging.getLogger(__name__)

MAX_PROGRESS_LINES = 500   # per session; a full run produces roughly 60-100


def graph_config(thread_id: str) -> dict:
    """Same config as run_graph.py, so API runs look the same in LangSmith."""
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": "arena_graph",
        "metadata": {"thread_id": thread_id, "source": "api"},
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GraphRunner:
    def __init__(self, graph):
        self.graph = graph
        self._lock = threading.Lock()              # guards the three dicts/sets below
        self._running: set[str] = set()
        self._progress: dict[str, list[dict]] = {}
        self._crashes: dict[str, str] = {}        # thread_id -> message, if a run died outside the graph's own recovery

    # --- read side (used by GET) ---

    def is_running(self, thread_id: str) -> bool:
        with self._lock:
            return thread_id in self._running

    def progress(self, thread_id: str) -> list[dict]:
        with self._lock:
            return list(self._progress.get(thread_id, []))

    def crash(self, thread_id: str) -> str | None:
        with self._lock:
            return self._crashes.get(thread_id)

    # --- write side (used by POST) ---

    def start(self, thread_id: str, graph_input) -> bool:
        """Start a background run. graph_input: the first input dict, a Command(resume=...), or None (continue).
        Returns False if this session already has a run going (check and claim happen under one lock)."""
        with self._lock:
            if thread_id in self._running:
                return False
            self._running.add(thread_id)
            self._crashes.pop(thread_id, None)
        threading.Thread(target=self._run, args=(thread_id, graph_input), daemon=True,
                         name=f"graph-{thread_id[:8]}").start()
        return True

    def _add_line(self, thread_id: str, node: str, message: str, at: str | None = None) -> None:
        with self._lock:
            lines = self._progress.setdefault(thread_id, [])
            lines.append({"at": at or _now(), "node": node, "message": message})
            del lines[:-MAX_PROGRESS_LINES]

    def _run(self, thread_id: str, graph_input) -> None:
        config = graph_config(thread_id)
        started = time.time()
        try:
            for mode, chunk in self.graph.stream(graph_input, config, stream_mode=["custom", "updates"]):
                if mode == "custom":                     # progress.report() from inside a node
                    self._add_line(thread_id, chunk.get("node", "?"), chunk.get("message", ""), chunk.get("at"))
                    continue
                for node, update in chunk.items():       # one entry per finished node
                    if node == "__interrupt__":
                        self._add_line(thread_id, "graph", f"paused: waiting for your input ({update[0].value.get('type')})")
                    else:
                        status = (update or {}).get("status")
                        self._add_line(thread_id, node, f"✔ finished after {time.time() - started:.0f}s"
                                                        + (f" (status {status})" if status else ""))
            self._save_status_if_paused(thread_id, config)
        except Exception as exc:                         # noqa: BLE001 - nodes catch their own errors; this is e.g. the DB
            log.exception("background run %s crashed", thread_id)
            message = f"{type(exc).__name__}: {str(exc)[:300]}"
            with self._lock:
                self._crashes[thread_id] = message
            self._add_line(thread_id, "graph", f"run crashed: {message}")
        finally:
            with self._lock:
                self._running.discard(thread_id)

    def _save_status_if_paused(self, thread_id: str, config: dict) -> None:
        """Finished runs are saved by the completion node (with metrics and report), so only pauses here."""
        if not get_settings().persist_results:
            return
        snapshot = self.graph.get_state(config)
        if snapshot.interrupts:
            try:
                save_session_status(thread_id, snapshot.values, snapshot.values.get("status", "unknown"))
            except Exception:                            # noqa: BLE001 - the checkpoint is the truth; the row is a copy
                log.exception("could not save session status for %s", thread_id)
