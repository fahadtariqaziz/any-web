"""M5: project_artifacts (approved briefs, later approved plans).

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('brief', 'plan')", name="ck_project_artifacts_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "kind", "content_hash", name="uq_project_artifacts_content"),
        sa.UniqueConstraint("thread_id", "kind", "version", name="uq_project_artifacts_version"),
    )
    op.create_index(op.f("ix_project_artifacts_thread_id"), "project_artifacts", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_artifacts_thread_id"), table_name="project_artifacts")
    op.drop_table("project_artifacts")
