"""Long-term memory (LTM): what the agents remember about a patient from one chat to the next.

Short-term memory is the graph state of ONE session (state.py + the Postgres checkpoint). Long-term memory
lives in the `patient_memories` table and is keyed by patient_id: an anonymous random id the browser keeps
in localStorage and sends as the X-Patient-Id header (no login, so "same browser = same patient").

Written:
- at the end of every session with a patient_id (completion): condition, profile facts and constraints, by
  Python, no LLM (remember_session);
- during the chat, when Claude calls the remember_fact tool (tools.py).
Read:
- when a session starts (API → state["patient_memories"]): intake and clarification see them, so a returning
  patient is not asked again what they already told us;
- by the chat agent on every turn (fresh from the database, so facts saved a minute ago are included).

Memory is a convenience: a database error never breaks a session or a chat turn, it only means "no memories".
"""

import logging
import re

from ai_decision_arena.db.repository import add_memories, delete_memories, list_memories
from ai_decision_arena.state import ArenaState

log = logging.getLogger(__name__)

MAX_FACT_CHARS = 300
MAX_SESSION_FACTS = 12
PATIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def valid_patient_id(value: str | None) -> str | None:
    """The header comes from the browser: accept only a plain id (a UUID in practice), else ignore it."""
    return value if value and PATIENT_ID_PATTERN.match(value) else None


def load(patient_id: str | None) -> list[str]:
    if not patient_id:
        return []
    try:
        return [m.fact for m in list_memories(patient_id)]
    except Exception:                                    # noqa: BLE001 - see module docstring
        log.exception("could not load memories for %s", patient_id)
        return []


def remember(patient_id: str | None, facts: list[str], source: str, thread_id: str | None = None) -> int:
    """Save facts (trimmed, de-duplicated). Returns how many were offered; 0 without a patient id."""
    clean = list(dict.fromkeys(f.strip()[:MAX_FACT_CHARS] for f in facts if f and f.strip()))
    if not patient_id or not clean:
        return 0
    try:
        add_memories(patient_id, clean, source, thread_id)
    except Exception:                                    # noqa: BLE001
        log.exception("could not save memories for %s", patient_id)
        return 0
    return len(clean)


def forget(patient_id: str) -> int:
    return delete_memories(patient_id)


def session_facts(state: ArenaState) -> list[str]:
    """Stable facts from a finished session, worth knowing next time (no symptoms: they change)."""
    facts = []
    if state.get("condition_name"):
        facts.append(f"condition: {state['condition_name']}")
    for key, value in (state.get("health_profile") or {}).items():
        facts.append(f"{key}: {value}")
    for key, value in (state.get("constraints") or {}).items():
        facts.append(f"{key} (constraint): {value}")
    return facts[:MAX_SESSION_FACTS]


def remember_session(state: ArenaState, thread_id: str) -> int:
    return remember(state.get("patient_id"), session_facts(state), "onboarding", thread_id)


def memories_block(facts: list[str]) -> str:
    """For prompts. Empty string when there is nothing to remember (first visit)."""
    if not facts:
        return ""
    lines = "\n".join(f"- {f}" for f in facts)
    return f"<remembered_from_earlier_chats>\n{lines}\n</remembered_from_earlier_chats>"
