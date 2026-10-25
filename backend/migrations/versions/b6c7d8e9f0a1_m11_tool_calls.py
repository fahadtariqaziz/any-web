"""M11 part 2: tool_calls (agent tool decisions, sandbox commands, Ask tools, research searches).

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("timed_out", sa.Boolean(), nullable=False),
        sa.Column("duration_seconds", sa.Double(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('agent', 'sandbox', 'chat', 'search')", name="ck_tool_calls_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_thread_id", "tool_calls", ["thread_id"])
    op.create_index("ix_tool_calls_at", "tool_calls", ["at"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_at", table_name="tool_calls")
    op.drop_index("ix_tool_calls_thread_id", table_name="tool_calls")
    op.drop_table("tool_calls")
