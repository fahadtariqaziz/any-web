"""The app's own tables (docs/requirements.md §9, adapted to health).

LangGraph's checkpoint tables hold the graph's working state; these tables hold what we want to
QUERY: sessions and their status, kept evidence, final reports, (Phase 8) user feedback, and the patient
chat's messages (chat_messages, written by api/chat.py).
We don't copy every state field: the full state stays in the checkpoint, keyed by thread_id.

Schema changes go through Alembic migrations (backend/migrations), never by hand.
"""

import uuid
from datetime import datetime

from sqlalchemy import (CheckConstraint, Computed, DateTime, Double, ForeignKey, Index, Integer, String, Text,
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
    mode: Mapped[str] = mapped_column(String(10), server_default="full", index=True)   # full (admin) / quick (patient chat)
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
    domain: Mapped[str] = mapped_column(String(20))           # research / doctor / patient
    source_url: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40))
    excerpt: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(30))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)     # strength, claims, limitations, patient context...

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
    """One message of the patient chat that follows onboarding (quick sessions). The onboarding itself
    (first message, questions and answers, summary) lives in the checkpoint; only the free chat is here.
    Linked by thread_id (not a foreign key): the chat works even when PERSIST_RESULTS=false skips the session row."""

    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), server_default="reply")   # "reply" | "check_in" (triggers.py)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserMemory(Base):
    """Long-term memory: one remembered fact about a patient, kept across chats (memory.py).
    user_id is the anonymous id the browser keeps in localStorage: no login, so "same browser = same patient"."""

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


class KnowledgeDoc(Base):
    """The knowledge base (knowledge.py): documents the chat agent can search, with Postgres full-text search.

    kind "curated": hand-written docs from backend/knowledge/*.md (scripts/load_knowledge.py).
    kind "evidence": every kept source of every finished session (saved at completion), so the knowledge base
    grows with each session. `key` makes re-loading idempotent: the file name, or "<thread_id>:<evidence_id>".
    `search_vector` is computed by Postgres itself from title + content (weights: title A, content B)."""

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
    domain: Mapped[str | None] = mapped_column(String(20))      # research / doctor / patient (evidence only)
    condition: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(String(64), index=True)
    search_vector: Mapped[str] = mapped_column(TSVECTOR, Computed(
        "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('english', coalesce(condition, '') || ' ' || content), 'B')", persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
