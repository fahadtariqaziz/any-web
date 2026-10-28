"""Writes to the app's own tables. Every write is idempotent ("insert ... on conflict update"), so
saving the same session twice (a retry, a repeated request) updates rows instead of duplicating them.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from ai_decision_arena.db.engine import session_factory
from ai_decision_arena.db.models import (ChatMessage, DecisionReport, DecisionSession, EvidenceRecord, KnowledgeDoc,
                                         ProjectArtifact, ProjectRuntime, ToolCall, UsageEvent, UserMemory)

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
        plan_stack = ", ".join((state.get("implementation_plan") or {}).get("tech_stack") or [])[:200] or None
        _upsert_knowledge(db, [
            {"kind": "evidence", "key": f"{thread_id}:{e['evidence_id']}", "title": e["source_title"],
             "url": str(e["source_url"]), "domain": e["domain"], "topic": state.get("project_name"),
             "content": " ".join([e.get("relevant_excerpt", ""), *e.get("claims_supported", [])]), "thread_id": thread_id,
             "status": "verified", "verified_at": datetime.now(timezone.utc), "stack": plan_stack}
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


def save_artifact(thread_id: str, kind: str, markdown: str, content: dict, content_hash: str, approved_at: str) -> int:
    """Store an approved brief / plan as the next version; returns its version. The same content again (same hash)
    returns the existing version instead of adding a row."""
    with session_factory().begin() as db:
        existing = db.execute(select(ProjectArtifact.version).where(
            ProjectArtifact.thread_id == thread_id, ProjectArtifact.kind == kind,
            ProjectArtifact.content_hash == content_hash)).scalar_one_or_none()
        if existing is not None:
            return existing
        latest = db.execute(select(func.max(ProjectArtifact.version)).where(
            ProjectArtifact.thread_id == thread_id, ProjectArtifact.kind == kind)).scalar_one_or_none() or 0
        db.add(ProjectArtifact(thread_id=thread_id, kind=kind, version=latest + 1, content_hash=content_hash,
                               markdown=markdown, content=content, approved_at=datetime.fromisoformat(approved_at)))
        return latest + 1


def list_artifacts(thread_id: str, kind: str | None = None) -> list[ProjectArtifact]:
    query = select(ProjectArtifact).where(ProjectArtifact.thread_id == thread_id).order_by(ProjectArtifact.kind, ProjectArtifact.version)
    if kind:
        query = query.where(ProjectArtifact.kind == kind)
    with session_factory()() as db:
        return list(db.execute(query).scalars())


RUNTIME_COLUMNS = ("state", "command", "port", "pid", "process_started_at", "url", "last_error", "log_path",
                   "started_at", "ready_at", "stopped_at", "last_seen_at")


def save_runtime(thread_id: str, values: dict) -> None:
    """Insert or update the session's runtime row (workspace/processes.py owns the values)."""
    row = {"thread_id": thread_id} | {k: values.get(k) for k in RUNTIME_COLUMNS}
    stmt = insert(ProjectRuntime).values(**row)
    stmt = stmt.on_conflict_do_update(index_elements=["thread_id"],
                                      set_={k: stmt.excluded[k] for k in RUNTIME_COLUMNS} | {"updated_at": func.now()})
    with session_factory().begin() as db:
        db.execute(stmt)


def _runtime_dict(row: ProjectRuntime) -> dict:
    return {"thread_id": row.thread_id} | {k: getattr(row, k) for k in RUNTIME_COLUMNS}


def get_runtime(thread_id: str) -> dict | None:
    with session_factory()() as db:
        row = db.execute(select(ProjectRuntime).where(ProjectRuntime.thread_id == thread_id)).scalar_one_or_none()
        return _runtime_dict(row) if row else None


def list_runtimes(states: tuple[str, ...] = ("starting", "ready")) -> list[dict]:
    with session_factory()() as db:
        rows = db.execute(select(ProjectRuntime).where(ProjectRuntime.state.in_(states))).scalars()
        return [_runtime_dict(r) for r in rows]


def list_sessions(limit: int = 20, mode: str | None = None) -> list[DecisionSession]:
    """Newest sessions first, for the projects lists. mode: only "full" or legacy "quick" ones."""
    query = select(DecisionSession).order_by(DecisionSession.created_at.desc()).limit(limit)
    if mode:
        query = query.where(DecisionSession.mode == mode)
    if mode == "quick":   # legacy chats whose first message intake rejected: nothing to reopen
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
    """Insert facts; a fact the user already has is skipped (unique user_id + fact)."""
    if not facts:
        return
    rows = [{"user_id": user_id, "fact": f, "source": source, "thread_id": thread_id} for f in facts]
    with session_factory().begin() as db:
        db.execute(insert(UserMemory).values(rows).on_conflict_do_nothing(constraint="uq_user_memories_fact"))


def prune_memories(user_id: str, keep: int) -> int:
    """Delete every fact of this user beyond the newest `keep` (review 2026-10-29: a bounded memory, like a bounded
    context). Returns how many were deleted."""
    newest = select(UserMemory.id).where(UserMemory.user_id == user_id).order_by(UserMemory.id.desc()).limit(keep)
    with session_factory().begin() as db:
        return db.execute(delete(UserMemory).where(UserMemory.user_id == user_id,
                                                   UserMemory.id.not_in(newest))).rowcount


def list_memories(user_id: str, limit: int = 40) -> list[UserMemory]:
    """The newest `limit` facts, oldest first (so the prompt reads like a history)."""
    query = (select(UserMemory).where(UserMemory.user_id == user_id)
             .order_by(UserMemory.id.desc()).limit(limit))
    with session_factory()() as db:
        return list(reversed(db.execute(query).scalars().all()))


def delete_memories(user_id: str, thread_id: str | None = None, source: str | None = None) -> int:
    """"Forget me": every remembered fact of this user; with thread_id / source only those (a project's own session
    facts, replaced when it completes again). Returns how many were deleted."""
    query = delete(UserMemory).where(UserMemory.user_id == user_id)
    if thread_id:
        query = query.where(UserMemory.thread_id == thread_id)
    if source:
        query = query.where(UserMemory.source == source)
    with session_factory().begin() as db:
        return db.execute(query).rowcount


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


def replace_curated_docs(rows: list[dict]) -> int:
    """Upsert the curated docs and delete curated rows whose file is gone (e.g. the old health docs). Returns how
    many were deleted."""
    with session_factory().begin() as db:
        _upsert_knowledge(db, rows)
        result = db.execute(delete(KnowledgeDoc).where(KnowledgeDoc.kind == "curated",
                                                       KnowledgeDoc.key.not_in([r["key"] for r in rows] or [""])))
        return result.rowcount


# Full-text search. plainto_tsquery joins the words with AND ("&"), so a whole question would only match a
# document containing every word; turning "&" into "|" (OR) lets ts_rank reward documents that match MORE words.
# Documents of the current project get a boost (they were found for this very project).
SEARCH_SQL = text("""
SELECT id, kind, title, url, domain, topic, thread_id, content, status, verified_at, stack,
       ts_rank(search_vector, q) * CASE WHEN thread_id = :thread_id THEN 1.5 ELSE 1 END AS rank
FROM knowledge_docs,
     to_tsquery('english', replace(plainto_tsquery('english', :query)::text, ' & ', ' | ')) AS q
WHERE search_vector @@ q
  AND (:include_curated OR kind = 'evidence')
  AND status <> 'deprecated'
ORDER BY rank DESC
LIMIT :limit
""")


# --- triggers (triggers.py) ---------------------------------------------------------------------

def backfill_knowledge_from_evidence() -> int:
    """Copy the evidence of sessions saved BEFORE the knowledge base existed (new sessions do it at completion)."""
    with session_factory().begin() as db:
        return db.execute(text("""
            INSERT INTO knowledge_docs (kind, key, title, url, domain, topic, content, thread_id)
            SELECT 'evidence', s.thread_id || ':' || e.evidence_id, e.source_title, e.source_url, e.domain,
                   s.project_name, e.excerpt, s.thread_id
            FROM evidence_records e JOIN decision_sessions s ON s.id = e.session_id
            ON CONFLICT ON CONSTRAINT uq_knowledge_docs_kind_key DO NOTHING""")).rowcount


def search_knowledge_docs(query: str, thread_id: str | None, limit: int, include_curated: bool = True) -> list[dict]:
    with session_factory()() as db:
        rows = db.execute(SEARCH_SQL, {"query": query, "thread_id": thread_id or "", "limit": limit,
                                       "include_curated": include_curated}).mappings()
        return [dict(r) for r in rows]


USAGE_COLUMNS = ("seconds", "calls", "failed_calls", "models", "input_tokens", "output_tokens", "cache_read_tokens",
                 "cache_write_tokens", "cost_usd", "error")


def save_usage_event(thread_id: str, entry: dict) -> None:
    """One usage entry (usage.UsageMeter.entry) as a row."""
    with session_factory().begin() as db:
        db.add(UsageEvent(thread_id=thread_id, node=entry["node"], at=datetime.fromisoformat(entry["at"]),
                          **{k: entry.get(k) for k in USAGE_COLUMNS if entry.get(k) is not None}))


def usage_metrics(since: datetime) -> dict:
    """Totals since `since`: overall, per node, per model (calls), per day; failures per node."""
    sums = (func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.calls), 0),
            func.coalesce(func.sum(UsageEvent.failed_calls), 0), func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0), func.coalesce(func.sum(UsageEvent.cache_read_tokens), 0),
            func.coalesce(func.sum(UsageEvent.cache_write_tokens), 0), func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
            func.coalesce(func.sum(UsageEvent.seconds), 0.0),
            func.count(UsageEvent.error))
    keys = ("runs", "calls", "failed_calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
            "cost_usd", "seconds", "node_failures")

    def row_dict(row) -> dict:
        d = dict(zip(keys, row))
        d["cost_usd"], d["seconds"] = round(float(d["cost_usd"]), 4), round(float(d["seconds"]), 1)
        return d

    where = UsageEvent.at >= since
    day = func.date_trunc("day", UsageEvent.at)
    with session_factory()() as db:
        total = row_dict(db.execute(select(*sums).where(where)).one())
        total["sessions"] = db.execute(select(func.count(func.distinct(UsageEvent.thread_id))).where(where)).scalar_one()
        by_node = [{"node": r[0], **row_dict(r[1:])} for r in
                   db.execute(select(UsageEvent.node, *sums).where(where).group_by(UsageEvent.node)
                              .order_by(func.sum(UsageEvent.cost_usd).desc()))]
        by_day = [{"day": r[0].date().isoformat(), **row_dict(r[1:])} for r in
                  db.execute(select(day, *sums).where(where).group_by(day).order_by(day))]
        models: dict[str, int] = {}
        for (m,) in db.execute(select(UsageEvent.models).where(where)):
            for name, n in (m or {}).items():
                models[name] = models.get(name, 0) + int(n)
    return {"total": total, "by_node": by_node, "by_day": by_day, "calls_by_model": models}


def session_node_cost(thread_id: str, node: str) -> float:
    """USD one node spent in a session (used for Ask: its replies are not in the checkpoint)."""
    with session_factory()() as db:
        return round(float(db.execute(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
            UsageEvent.thread_id == thread_id, UsageEvent.node == node)).scalar_one()), 4)


def agent_cost_since(since: datetime) -> dict:
    """Coding-agent spend of sessions completed since `since` (decision_sessions.metrics, written at completion)."""
    cost = DecisionSession.metrics["implementation_cost_usd"].as_float()
    with session_factory()() as db:
        n, total = db.execute(select(func.count(DecisionSession.id), func.coalesce(func.sum(cost), 0.0)).where(
            DecisionSession.completed_at >= since, DecisionSession.metrics.has_key("implementation_cost_usd"))).one()
    return {"sessions": n, "cost_usd": round(float(total), 4)}


def save_tool_call(row: dict) -> None:
    with session_factory().begin() as db:
        db.add(ToolCall(**{**row, "at": datetime.fromisoformat(row["at"])}))


def list_tool_calls(thread_id: str, limit: int = 300, source: str | None = None) -> list[ToolCall]:
    query = select(ToolCall).where(ToolCall.thread_id == thread_id).order_by(ToolCall.at.desc(), ToolCall.id.desc())
    if source:
        query = query.where(ToolCall.source == source)
    with session_factory()() as db:
        return list(db.execute(query.limit(limit)).scalars())


def tool_metrics(since: datetime) -> list[dict]:
    """Per source + tool: calls, failures (not ok), refused/denied (a reason without an exit code), timeouts, seconds."""
    refused = (~ToolCall.ok) & ToolCall.exit_code.is_(None) & ~ToolCall.timed_out
    rows = select(ToolCall.source, ToolCall.tool, func.count(ToolCall.id),
                  func.count(ToolCall.id).filter(~ToolCall.ok), func.count(ToolCall.id).filter(refused),
                  func.count(ToolCall.id).filter(ToolCall.timed_out),
                  func.coalesce(func.avg(ToolCall.duration_seconds), 0.0)).where(ToolCall.at >= since).group_by(
        ToolCall.source, ToolCall.tool).order_by(ToolCall.source, func.count(ToolCall.id).desc())
    with session_factory()() as db:
        return [{"source": s, "tool": tl, "calls": n, "failed": f, "refused": r, "timed_out": to,
                 "avg_seconds": round(float(avg), 3)} for s, tl, n, f, r, to, avg in db.execute(rows)]
