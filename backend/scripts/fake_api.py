"""An OFFLINE backend for UI work: the real API and graph with the test fakes (no Claude, no Tavily, no database).

The whole pipeline runs in seconds and for free: fake LLM (tests/conftest.py builds valid outputs from the prompt
text), fake search, fake coding agent (writes the task's files); the build check and the preview dev server
(`python3 -m http.server {port}`) run for REAL in a throwaway generated-projects folder. Ask mode answers with a
canned text, chat messages and the project list live in memory. Use it to click through every pause of the
builder UI without paying for a live run.

    cd backend && uv run python scripts/fake_api.py            # API on http://localhost:8002
    cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8002 npx next build && npx next start -p 3002
    # (next start, not a second `next dev`: the user's dev server on 3001 owns .next/dev)

Never point it at the real database: the conftest environment (imported first) sets a dead DATABASE_URL.
"""

import importlib
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests.conftest as fakes  # noqa: E402  (FIRST: sets the test environment before the package is imported)

import uvicorn  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from ai_decision_arena.api import chat as chat_api  # noqa: E402
from ai_decision_arena.api import main as api_main  # noqa: E402
from ai_decision_arena.api.runner import GraphRunner  # noqa: E402
from ai_decision_arena.graph import build_graph  # noqa: E402
from ai_decision_arena.workspace.processes import MemoryRuntimeStore, ProcessManager, set_manager  # noqa: E402

PORT = 8002
MESSAGES: dict[str, list[SimpleNamespace]] = {}
SESSIONS: list[SimpleNamespace] = []


def install_fakes() -> None:
    fake = fakes.FakeLLM()
    for module in fakes.LLM_USERS:
        importlib.import_module(module).call_structured = fake
    import ai_decision_arena.nodes.implementer as implementer
    import ai_decision_arena.nodes.planner as planner
    import ai_decision_arena.nodes.research as research
    planner.resolve_model = implementer.resolve_model = lambda wanted: (wanted, "")
    implementer.run_agent_task = fakes.FakeAgent()
    research.run_searches = fakes.fake_run_searches

    # Ask mode and the project list without a database.
    def add_message(thread_id, role, content, kind="reply"):
        MESSAGES.setdefault(thread_id, []).append(SimpleNamespace(role=role, content=content, created_at=datetime.now(timezone.utc)))

    def stream_reply(thread_id, values, history, message):
        yield "(offline fake API) I would answer about "
        yield f"{values.get('project_name') or 'your project'} here. You asked: {message[:80]}"

    chat_api.list_chat_messages = lambda thread_id: MESSAGES.get(thread_id, [])
    chat_api.add_chat_message = add_message
    chat_api.stream_reply = stream_reply

    real_start = api_main._start

    def start(runner, thread_id, inputs):
        if not isinstance(inputs, dict):                    # resume (Command) or continue (None): not a new session
            return real_start(runner, thread_id, inputs)
        now = datetime.now(timezone.utc)
        SESSIONS.insert(0, SimpleNamespace(thread_id=thread_id, question=inputs["question"], mode=inputs.get("mode", "full"),
                                           project_name=None, status="intake", risk_flags=[], created_at=now,
                                           updated_at=None, completed_at=None))
        return real_start(runner, thread_id, inputs)

    api_main._start = start
    api_main.list_sessions = lambda limit=20, mode=None: SESSIONS[:limit]


@asynccontextmanager
async def offline_lifespan(application):
    graph = build_graph(checkpointer=InMemorySaver())
    application.state.graph = graph
    application.state.runner = GraphRunner(graph)
    manager = ProcessManager(store=MemoryRuntimeStore())
    set_manager(manager)
    application.state.processes = manager
    try:
        yield
    finally:
        manager.stop_all()


if __name__ == "__main__":
    install_fakes()
    api_main.app.router.lifespan_context = offline_lifespan
    print(f"offline fake API on http://localhost:{PORT} (generated projects in {fakes.os.environ['GENERATED_PROJECTS_DIR']})")
    uvicorn.run(api_main.app, host="127.0.0.1", port=PORT, log_level="warning")
