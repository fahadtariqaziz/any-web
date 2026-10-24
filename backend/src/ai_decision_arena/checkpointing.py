"""Where the graph saves its checkpoints (the full state after every step, keyed by thread_id).

InMemorySaver (Phases 1-6) loses everything when Python exits. PostgresSaver writes each checkpoint
to the `ai_decision_arena` database, so a session paused at a clarification question can be
resumed later from a new process (needed by the FastAPI backend in Phase 8).

Usage:
    with postgres_checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        ...   # use the graph INSIDE the with-block: the saver holds an open connection
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from ai_decision_arena.config import get_settings


@contextmanager
def postgres_checkpointer() -> Iterator[PostgresSaver]:
    """Open a connection to DATABASE_URL, make sure LangGraph's tables exist, yield the saver.
    The connection is closed when the with-block ends, even after an error or Ctrl+C."""
    with PostgresSaver.from_conn_string(get_settings().database_url) as saver:
        # Creates checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations.
        # Safe to call every time: already-applied migrations are skipped.
        saver.setup()
        yield saver
