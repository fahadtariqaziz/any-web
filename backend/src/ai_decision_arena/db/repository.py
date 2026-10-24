"""Writes to the app's own tables. Every write is idempotent ("insert ... on conflict update"), so
saving the same session twice (a retry, a repeated request) updates rows instead of duplicating them.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from ai_decision_arena.db.engine import session_factory
from ai_decision_arena.db.models import (ChatMessage, DecisionReport, DecisionSession, EvidenceRecord, KnowledgeDoc,
                                         UserMemory)

EVIDENCE_COLUMNS = {"evidence_id", "domain", "source_url", "source_title", "source_type",
                    "relevant_excerpt", "verification_status", "retrieved_at"}


def _upsert_session(db, thread_id: str, state: dict, status: str, metrics: dict | None):
    values = {
        "thread_id": thread_id,
        "user_id": state.get("user_id") or None,
        "question": state.get("question", ""),
        "mode": state.get("mode") or "full",
        "project_name": state.get("project_name"),
        "project_category": state.get("project_category"),
        "status": status,
        "risk_flags": state.get("risk_flags", []),
        "metrics": metrics or {},
        "completed_at": datetime.now(timezone.utc) if metrics is not None else None,
    }
    stmt = insert(DecisionSession).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["thread_id"],
        set_={k: stmt.excluded[k] for k in values if k != "thread_id"} | {"updated_at": datetime.now(timezone.utc)},
    ).returning(DecisionSession.id)
    return db.execute(stmt).scalar_one()


def save_session_status(thread_id: str, state: dict, status: str) -> None:
    """The API (Phase 8) calls this when a session starts and at every pause, so decision_sessions shows
    live statuses, not only finished sessions. Leaves metrics / completed_at alone: completion owns those."""
    values = {
        "thread_id": thread_id,
        "user_id": state.get("user_id") or None,
        "question": state.get("question", ""),
        "mode": state.get("mode") or "full",
        "project_name": state.get("project_name"),
        "project_category": state.get("project_category"),
        "status": status,
        "risk_flags": state.get("risk_flags", []),
    }
    with session_factory().begin() as db:
        stmt = insert(DecisionSession).values(**values)
        db.execute(stmt.on_conflict_do_update(
            index_elements=["thread_id"],
            set_={k: stmt.excluded[k] for k in values if k != "thread_id"} | {"updated_at": datetime.now(timezone.utc)},
        ))


def save_completion(thread_id: str, state: dict, status: str, metrics: dict) -> None:
    """Session + evidence + report in ONE transaction: all saved, or nothing (rollback on any error)."""
    with session_factory().begin() as db:
        session_id = _upsert_session(db, thread_id, state, status, metrics)

        rows = [
            {
                "session_id": session_id,
                "evidence_id": e["evidence_id"],
                "domain": e["domain"],
                "source_url": str(e["source_url"]),
                "source_title": e["source_title"],
                "source_type": e["source_type"],
                "excerpt": e.get("relevant_excerpt", ""),
                "verification_status": e.get("verification_status", "pending"),
                "retrieved_at": e.get("retrieved_at"),
                "details": {k: v for k, v in e.items() if k not in EVIDENCE_COLUMNS},
            }
            for e in state.get("evidence", [])
        ]
        if rows:
            stmt = insert(EvidenceRecord).values(rows)
            db.execute(stmt.on_conflict_do_update(
                constraint="uq_evidence_session_evidence_id",
                set_={c: stmt.excluded[c] for c in rows[0] if c not in ("session_id", "evidence_id")},
            ))

        # The knowledge base grows with every session: its evidence becomes searchable for later chats.
        _upsert_knowledge(db, [
            {"kind": "evidence", "key": f"{thread_id}:{e['evidence_id']}", "title": e["source_title"],
             "url": str(e["source_url"]), "domain": e["domain"], "condition": state.get("project_name"),
             "content": " ".join([e.get("relevant_excerpt", ""), *e.get("claims_supported", [])]), "thread_id": thread_id}
            for e in state.get("evidence", [])
        ])

        report = state.get("final_report")
        if report:
            stmt = insert(DecisionReport).values(session_id=session_id, status=status,
                                                 is_conditional=bool(report.get("is_conditional")), report_json=report)
            db.execute(stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_={"status": stmt.excluded.status, "is_conditional": stmt.excluded.is_conditional,
                      "report_json": stmt.excluded.report_json},
            ))


def list_sessions(limit: int = 20, mode: str | None = None) -> list[DecisionSession]:
    """Newest sessions first, for the frontend's "recent sessions" lists. mode: only "full" or "quick" ones."""
    query = select(DecisionSession).order_by(DecisionSession.created_at.desc()).limit(limit)
    if mode:
        query = query.where(DecisionSession.mode == mode)
    if mode == "quick":   # chats whose first message intake rejected (not about health): nothing to reopen
        query = query.where(~((DecisionSession.status == "failed") & DecisionSession.project_name.is_(None)))
    with session_factory()() as db:
        return list(db.execute(query).scalars())


def add_chat_message(thread_id: str, role: str, content: str, kind: str = "reply") -> None:
    with session_factory().begin() as db:
        db.add(ChatMessage(thread_id=thread_id, role=role, content=content, kind=kind))


def list_chat_messages(thread_id: str, limit: int = 200) -> list[ChatMessage]:
    """Oldest first (the order of the conversation)."""
    query = select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.id).limit(limit)
    with session_factory()() as db:
        return list(db.execute(query).scalars())


# --- long-term memory (memory.py) ---------------------------------------------------------------

def add_memories(user_id: str, facts: list[str], source: str, thread_id: str | None) -> None:
    """Insert facts; a fact the patient already has is skipped (unique user_id + fact)."""
    if not facts:
        return
    rows = [{"user_id": user_id, "fact": f, "source": source, "thread_id": thread_id} for f in facts]
    with session_factory().begin() as db:
        db.execute(insert(UserMemory).values(rows).on_conflict_do_nothing(constraint="uq_user_memories_fact"))


def list_memories(user_id: str, limit: int = 40) -> list[UserMemory]:
    """The newest `limit` facts, oldest first (so the prompt reads like a history)."""
    query = (select(UserMemory).where(UserMemory.user_id == user_id)
             .order_by(UserMemory.id.desc()).limit(limit))
    with session_factory()() as db:
        return list(reversed(db.execute(query).scalars().all()))


def delete_memories(user_id: str) -> int:
    """"Forget me": removes every remembered fact of this patient. Returns how many were deleted."""
    with session_factory().begin() as db:
        return db.execute(delete(UserMemory).where(UserMemory.user_id == user_id)).rowcount


# --- knowledge base (knowledge.py) --------------------------------------------------------------

def _upsert_knowledge(db, rows: list[dict]) -> None:
    if not rows:
        return
    stmt = insert(KnowledgeDoc).values(rows)
    db.execute(stmt.on_conflict_do_update(
        constraint="uq_knowledge_docs_kind_key",
        set_={c: stmt.excluded[c] for c in rows[0] if c not in ("kind", "key")},
    ))


def upsert_knowledge_docs(rows: list[dict]) -> None:
    with session_factory().begin() as db:
        _upsert_knowledge(db, rows)


# Full-text search. plainto_tsquery joins the words with AND ("&"), so a whole question would only match a
# document containing every word; turning "&" into "|" (OR) lets ts_rank reward documents that match MORE words.
# Documents of the current chat get a boost (they were found for this very patient).
SEARCH_SQL = text("""
SELECT id, kind, title, url, domain, condition, thread_id, content,
       ts_rank(search_vector, q) * CASE WHEN thread_id = :thread_id THEN 1.5 ELSE 1 END AS rank
FROM knowledge_docs,
     to_tsquery('english', replace(plainto_tsquery('english', :query)::text, ' & ', ' | ')) AS q
WHERE search_vector @@ q
ORDER BY rank DESC
LIMIT :limit
""")


# --- triggers (triggers.py) ---------------------------------------------------------------------

# Finished patient chats that have been quiet for at least :quiet_hours and whose last message is not already
# a check-in (so a patient who doesn't answer gets ONE check-in, not one per scheduler run).
QUIET_CHATS_SQL = text("""
SELECT s.thread_id
FROM decision_sessions s
LEFT JOIN LATERAL (
    SELECT m.kind, m.created_at FROM chat_messages m WHERE m.thread_id = s.thread_id ORDER BY m.id DESC LIMIT 1
) last ON true
WHERE s.mode = 'quick'
  AND s.status IN ('completed', 'completed_with_uncertainty')
  AND coalesce(last.created_at, s.completed_at) < now() - make_interval(secs => :quiet_hours * 3600)
  AND coalesce(last.kind, 'reply') <> 'check_in'
ORDER BY coalesce(last.created_at, s.completed_at) DESC
LIMIT :limit
""")


def quiet_chats(quiet_hours: float, limit: int) -> list[str]:
    with session_factory()() as db:
        return list(db.execute(QUIET_CHATS_SQL, {"quiet_hours": quiet_hours, "limit": limit}).scalars())


def backfill_knowledge_from_evidence() -> int:
    """Copy the evidence of sessions saved BEFORE the knowledge base existed (new sessions do it at completion)."""
    with session_factory().begin() as db:
        return db.execute(text("""
            INSERT INTO knowledge_docs (kind, key, title, url, domain, condition, content, thread_id)
            SELECT 'evidence', s.thread_id || ':' || e.evidence_id, e.source_title, e.source_url, e.domain,
                   s.project_name, e.excerpt, s.thread_id
            FROM evidence_records e JOIN decision_sessions s ON s.id = e.session_id
            ON CONFLICT ON CONSTRAINT uq_knowledge_docs_kind_key DO NOTHING""")).rowcount


def search_knowledge_docs(query: str, thread_id: str | None, limit: int) -> list[dict]:
    with session_factory()() as db:
        rows = db.execute(SEARCH_SQL, {"query": query, "thread_id": thread_id or "", "limit": limit}).mappings()
        return [dict(r) for r in rows]
