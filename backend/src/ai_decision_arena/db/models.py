"""The app's own tables (started from docs/requirements.md §9 of the health app; builder tables since M1).

LangGraph's checkpoint tables hold the graph's working state; these tables hold what we want to
QUERY: sessions and their status, kept evidence, final reports, user feedback, Ask-mode messages
(chat_messages, written by api/chat.py), memories, approved brief / plan versions, previews, usage and tool calls.
We don't copy every state field: the full state stays in the checkpoint, keyed by thread_id.

Schema changes go through Alembic migrations (backend/migrations), never by hand.
"""

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Computed, DateTime, Double, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DecisionSession(Base):
    """One row per graph session (thread_id)."""

    __tablename__ = "decision_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)   # links to the checkpoints
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)        # anonymous browser id (memory.py)
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10), server_default="full", index=True)   # full; legacy "quick" rows from the health app
    project_name: Mapped[str | None] = mapped_column(String(200))
    project_category: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), index=True)                   # a WorkflowStatus value
    risk_flags: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)                    # rounds, retries, seconds...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # cascade: deleting a session deletes its evidence, report and feedback too (in Python and in the DB).
    evidence: Mapped[list["EvidenceRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    report: Mapped["DecisionReport | None"] = relationship(back_populates="session", cascade="all, delete-orphan")
    feedback: Mapped[list["UserFeedback"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class EvidenceRecord(Base):
    """One row per kept source of a session (ev_001, ev_002, ...)."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        UniqueConstraint("session_id", "evidence_id", name="uq_evidence_session_evidence_id"),
        Index("ix_evidence_verification_status", "verification_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str] = mapped_column(String(20))
    domain: Mapped[str] = mapped_column(String(20))           # apps / papers / tech
    source_url: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40))
    excerpt: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(30))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)     # strength, claims, limitations, feedback context...

    session: Mapped[DecisionSession] = relationship(back_populates="evidence")


class DecisionReport(Base):
    """The final report. UNIQUE per session, so saving twice updates instead of duplicating."""

    __tablename__ = "decision_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(40))                # completed / completed_with_uncertainty
    is_conditional: Mapped[bool]
    report_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[DecisionSession] = relationship(back_populates="report")


class UserFeedback(Base):
    """Ratings / comments from the user. No writer yet: the feedback API endpoint comes in Phase 8."""

    __tablename__ = "user_feedback"
    __table_args__ = (CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="ck_feedback_rating_1_5"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_sessions.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str | None] = mapped_column(String(40))
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[DecisionSession] = relationship(back_populates="feedback")


class ChatMessage(Base):
    """One Ask-mode message of the builder chat. The rest of the conversation (first message, answers, reviews,
    change requests) lives in the checkpoint; only the free Ask exchange is here.
    Linked by thread_id (not a foreign key): the chat works even when PERSIST_RESULTS=false skips the session row."""

    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), server_default="reply")   # "reply" ("check_in": retired health trigger)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserMemory(Base):
    """Long-term memory: one remembered fact about a user, kept across projects (memory.py).
    user_id is the anonymous id the browser keeps in localStorage: no login, so "same browser = same user"."""

    __tablename__ = "user_memories"
    __table_args__ = (UniqueConstraint("user_id", "fact", name="uq_user_memories_fact"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    fact: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20))                 # "onboarding" (completion) | "chat" (remember_fact tool)
    thread_id: Mapped[str | None] = mapped_column(String(64))       # the chat it came from
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectArtifact(Base):
    """An approved version of a session's brief (M5) or implementation plan (M6), kept for the record and for later
    sessions (spec §10.6). One row per approval; version counts per (thread_id, kind). The same content approved twice
    (a node re-run after a crash) is stored once (unique content hash). Linked by thread_id like chat_messages."""

    __tablename__ = "project_artifacts"
    __table_args__ = (
        UniqueConstraint("thread_id", "kind", "version", name="uq_project_artifacts_version"),
        UniqueConstraint("thread_id", "kind", "content_hash", name="uq_project_artifacts_content"),
        CheckConstraint("kind IN ('brief', 'plan')", name="ck_project_artifacts_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))           # sha256 of markdown (what the user approved)
    markdown: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)       # ProblemBrief / ImplementationPlan as JSON
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectRuntime(Base):
    """The dev server (live preview) of a session (M7, workspace/processes.py). One row per session; the row is the
    registry that survives a backend restart: at startup a live process is adopted if its pid AND start time still
    match, otherwise the row is marked failed. Only one active (starting / ready) runtime may hold a port."""

    __tablename__ = "project_runtimes"
    __table_args__ = (
        CheckConstraint("state IN ('starting', 'ready', 'failed', 'stopped')", name="ck_project_runtimes_state"),
        Index("uq_project_runtimes_active_port", "port", unique=True,
              postgresql_where=text("state IN ('starting', 'ready')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20))
    command: Mapped[str] = mapped_column(Text)
    port: Mapped[int | None] = mapped_column(Integer)
    pid: Mapped[int | None] = mapped_column(Integer)
    process_started_at: Mapped[float | None] = mapped_column(Double)   # psutil create_time: guards against pid reuse
    url: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    log_path: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # preview viewed (idle stop)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UsageEvent(Base):
    """The builder's own model usage (M11, usage.py): one row per graph-node run that called a model, plus one per
    Ask reply (node "ask"). Feeds /api/metrics across sessions; per-session cost reads the checkpoint (usage_log).
    The coding agent's cost is not here (implementation_log)."""

    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_at", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    node: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))           # when the node run started
    seconds: Mapped[float] = mapped_column(Double, default=0.0)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, default=0)
    models: Mapped[dict] = mapped_column(JSONB, default=dict)               # model -> calls
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)           # uncached input
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Double, default=0.0)
    error: Mapped[str | None] = mapped_column(String(40))                   # ErrorRecord.category when the node failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolCall(Base):
    """One tool call of the builder's agents (M11 part 2, tool_log.py): coding-agent tool decisions, sandbox commands,
    Ask tools, research searches. Targets only (path / command / query), never outputs."""

    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_at", "at"), CheckConstraint(
        "source IN ('agent', 'sandbox', 'chat', 'search')", name="ck_tool_calls_source"))

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(10))
    tool: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(String(64), default="")             # task id / build step / hit count
    ok: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(Text)                        # denied / refused / failed because
    exit_code: Mapped[int | None] = mapped_column(Integer)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[float | None] = mapped_column(Double)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeDoc(Base):
    """The knowledge base (knowledge.py): documents the chat agent can search, with Postgres full-text search.

    kind "curated": hand-written docs from backend/knowledge/*.md (scripts/load_knowledge.py).
    kind "evidence": every kept source of every finished session (saved at completion), so the knowledge base
    grows with each session. `key` makes re-loading idempotent: the file name, or "<thread_id>:<evidence_id>".
    `search_vector` is computed by Postgres itself from title + content (weights: title A, content B).
    Freshness (review 2026-10-29): `status` verified | deprecated (deprecated rows are kept but never returned),
    `verified_at` (curated: the `verified:` date of the file; evidence: the session's completion), `stack` (comma
    keywords: a doc about Vite is boosted for a Vite project and ignored otherwise)."""

    __tablename__ = "knowledge_docs"
    __table_args__ = (
        UniqueConstraint("kind", "key", name="uq_knowledge_docs_kind_key"),
        CheckConstraint("kind IN ('curated', 'evidence')", name="ck_knowledge_docs_kind"),
        Index("ix_knowledge_docs_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(20))      # apps / papers / tech (evidence only)
    topic: Mapped[str | None] = mapped_column(String(200))      # curated: the doc's topic; evidence: the project name
    content: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), server_default="verified")       # verified | deprecated
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stack: Mapped[str | None] = mapped_column(String(200))                          # "vite, react" (curated) / the plan's stack
    search_vector: Mapped[str] = mapped_column(TSVECTOR, Computed(
        "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('english', coalesce(topic, '') || ' ' || content), 'B')", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
