"""Long-term memory (LTM): what the builder remembers about a user from one project to the next (spec §10.6).

Short-term memory is the graph state of ONE session (state.py + the Postgres checkpoint). Long-term memory
lives in the `user_memories` table and is keyed by user_id: an anonymous random id the browser keeps
in localStorage and sends as the X-User-Id header (no login, so "same browser = same user").

Written:
- at the end of every session with a user_id (completion): the project's name, profile facts and constraints, by
  Python, no LLM (remember_session). Each fact is prefixed with its project ("[project: ...]"), so a later project
  does not mistake another project's budget or audience for its own (spec: "do not mix unrelated project memories").
  When the same project completes again (reopened, changed), its earlier session facts are REPLACED: an approved
  change invalidates what was remembered before;
- in Ask mode, when Claude calls the remember_fact tool (tools.py): lasting preferences about the user (stack,
  budget, team), not tied to one project.
Read:
- when a session starts (API → state["user_memories"]): intake and clarification see them, so a returning
  user is not asked again what they already told us;
- by the Ask agent on every turn (fresh from the database, so facts saved a minute ago are included).
Deleted: "Forget me" (DELETE /api/memories) removes everything of the browser's user id.

Memory is a convenience: a database error never breaks a session or a chat turn, it only means "no memories".

Lifecycle (review 2026-10-29): extract (Python at completion, the assistant's remember_fact in Ask) → validate (each
fact carries its SOURCE in the prompt: "from your answers" = the user's own words, "noted by the assistant" = its
summary, so a model can weigh a guess below a confirmed fact) → scope (project-tagged vs user-level) → deduplicate
(unique user + fact) → version (a project's facts are replaced when it completes again) → retrieve (the newest 40,
each with its DATE, so an older fact loses to a newer one or to what the user says now) → expire (a cap of
MAX_MEMORIES_PER_USER, oldest first; "Forget me" deletes all).
"""

import logging
import re

from ai_decision_arena.db.repository import add_memories, delete_memories, list_memories, prune_memories
from ai_decision_arena.state import ArenaState

log = logging.getLogger(__name__)

MAX_FACT_CHARS = 300
MAX_SESSION_FACTS = 12
MAX_MEMORIES_PER_USER = 200
SOURCE_LABEL = {"onboarding": "from your answers", "chat": "noted by the assistant"}
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def valid_user_id(value: str | None) -> str | None:
    """The header comes from the browser: accept only a plain id (a UUID in practice), else ignore it."""
    return value if value and USER_ID_PATTERN.match(value) else None


def labelled(fact: str, source: str, created_at) -> str:
    """One fact as the prompt shows it: where it came from and when, then the fact."""
    when = created_at.date().isoformat() if created_at else "date unknown"
    return f"[{SOURCE_LABEL.get(source, source)}, {when}] {fact}"


def load(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    try:
        return [labelled(m.fact, m.source, m.created_at) for m in list_memories(user_id)]
    except Exception:                                    # noqa: BLE001 - see module docstring
        log.exception("could not load memories for %s", user_id)
        return []


def remember(user_id: str | None, facts: list[str], source: str, thread_id: str | None = None) -> int:
    """Save facts (trimmed, de-duplicated). Returns how many were offered; 0 without a user id."""
    clean = list(dict.fromkeys(f.strip()[:MAX_FACT_CHARS] for f in facts if f and f.strip()))
    if not user_id or not clean:
        return 0
    try:
        add_memories(user_id, clean, source, thread_id)
        if (dropped := prune_memories(user_id, MAX_MEMORIES_PER_USER)):
            log.info("memory cap: dropped the %d oldest fact(s) of %s", dropped, user_id)
    except Exception:                                    # noqa: BLE001
        log.exception("could not save memories for %s", user_id)
        return 0
    return len(clean)


def forget(user_id: str) -> int:
    return delete_memories(user_id)


def session_facts(state: ArenaState) -> list[str]:
    """Stable facts of a finished project, each labelled with the project they belong to."""
    name = (state.get("project_name") or "unnamed project").strip()[:80]
    tag = f"[project: {name}]"
    facts = [f"{tag} built this project" + (f" ({state['project_category']})" if state.get("project_category") else "")]
    for key, value in (state.get("project_profile") or {}).items():
        facts.append(f"{tag} {key}: {value}")
    for key, value in (state.get("constraints") or {}).items():
        facts.append(f"{tag} {key} (constraint): {value}")
    return facts[:MAX_SESSION_FACTS]


def remember_session(state: ArenaState, thread_id: str) -> int:
    """Replace this project's earlier session facts with the current ones (a reopened project may have changed)."""
    user_id = state.get("user_id")
    if user_id and thread_id:
        try:
            delete_memories(user_id, thread_id=thread_id, source="onboarding")
        except Exception:                                # noqa: BLE001 - see module docstring
            log.exception("could not replace the session facts of %s", thread_id)
    return remember(user_id, session_facts(state), "onboarding", thread_id)


def memories_block(facts: list[str]) -> str:
    """For prompts. Empty string when there is nothing to remember (first visit)."""
    if not facts:
        return ""
    lines = "\n".join(f"- {f}" for f in facts)
    note = ('each fact starts with where it came from (from your answers = the user said it; noted by the assistant = '
            'a summary it made) and the date; a newer fact or what the user says now wins over an older one')
    return f'<remembered_from_earlier_sessions note="{note}">\n{lines}\n</remembered_from_earlier_sessions>'
