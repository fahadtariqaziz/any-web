"""Triggers: what starts an agent besides a user typing.

1. User triggers (already there): POST /api/decisions starts onboarding, /resume continues it, a chat message
   starts a chat turn.
2. Scheduled trigger (this module): a background scheduler inside the API process looks every
   CHECK_IN_INTERVAL_SECONDS for patient chats that have been quiet for CHECK_IN_QUIET_HOURS and lets the
   chat agent write ONE short check-in ("How did the night-shift meals go?"). It shows up in the chat as a
   normal assistant message (kind "check_in"). A chat whose last message is already a check-in is skipped.
3. Manual trigger: POST /api/triggers/check-ins runs the same job now (for testing: quiet_hours=0).
4. Event trigger: a finished session (completion) saves its evidence to the knowledge base and its facts to
   long-term memory (db/repository.py, memory.py).

Cost guardrail: at most CHECK_IN_MAX_PER_RUN check-ins per run. CHECK_INS_ENABLED=false turns the scheduler off.
"""

import logging
import threading

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ai_decision_arena.api.runner import graph_config
from ai_decision_arena.chat import SYSTEM_PROMPT, build_context
from ai_decision_arena.config import get_settings
from ai_decision_arena.db.repository import add_chat_message, list_chat_messages, quiet_chats
from ai_decision_arena.llm import get_llm

log = logging.getLogger(__name__)

CHECK_IN_TOKENS = 300
CHECK_IN_INSTRUCTION = """(System trigger, not a message from the patient.) The patient has not written for a while.
Write ONE short, warm check-in message to them (2-3 sentences): refer to something specific from your conversation or
their plan (a meal idea, a habit they wanted to try, a question for their doctor), ask how it is going, and invite
them to share. No new advice, no lists, no disclaimers, no tools."""


def write_check_in(graph, thread_id: str) -> str | None:
    """One check-in for one chat. Returns the text, or None if the chat has no report (nothing to refer to)."""
    state = graph.get_state(graph_config(thread_id)).values or {}
    if not state.get("final_report"):
        return None
    history = [m for m in list_chat_messages(thread_id)][-10:]
    messages = [SystemMessage(content=SYSTEM_PROMPT.replace("{context}", build_context(state)))]
    # The conversation must start with a user turn: the onboarding summary stands in for it (it is in the context).
    messages.append(HumanMessage(content="(Onboarding finished; the summary above was shown to the patient.)"))
    for m in history:
        messages.append(HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content))
    messages.append(HumanMessage(content=CHECK_IN_INSTRUCTION))
    llm = get_llm(CHECK_IN_TOKENS, model=get_settings().chat_model)
    text = llm.invoke(messages, config={"run_name": "check_in_trigger", "metadata": {"thread_id": thread_id}}).text.strip()
    if text:
        add_chat_message(thread_id, "assistant", text, kind="check_in")
    return text or None


def run_check_ins(graph, quiet_hours: float | None = None, thread_id: str | None = None) -> list[str]:
    """Write check-ins for quiet chats (or for one given chat). Returns the thread ids that got one."""
    settings = get_settings()
    if thread_id:
        candidates = [thread_id]
    else:
        hours = settings.check_in_quiet_hours if quiet_hours is None else quiet_hours
        candidates = quiet_chats(hours, settings.check_in_max_per_run)
    done = []
    for tid in candidates:
        try:
            if write_check_in(graph, tid):
                done.append(tid)
        except Exception:                                # noqa: BLE001 - one bad chat must not stop the others
            log.exception("check-in failed for %s", tid)
    if done:
        log.info("check-ins written: %s", done)
    return done


class CheckInScheduler:
    """A daemon thread: run_check_ins every interval until stop(). Event.wait() = a sleep that stop() can cut short."""

    def __init__(self, graph):
        self.graph = graph
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="check-in-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        interval = get_settings().check_in_interval_seconds
        while not self._stop.wait(interval):             # first run after one interval, not at startup
            run_check_ins(self.graph)
