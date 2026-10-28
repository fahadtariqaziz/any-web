"""Review 2026-10-29: knowledge_docs freshness metadata (status, verified_at, stack).

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_docs", sa.Column("status", sa.String(length=20), server_default="verified", nullable=False))
    op.add_column("knowledge_docs", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("knowledge_docs", sa.Column("stack", sa.String(length=200), nullable=True))
    # Evidence rows saved before this change: verified when their session completed (created_at).
    op.execute("UPDATE knowledge_docs SET verified_at = created_at WHERE kind = 'evidence' AND verified_at IS NULL")


def downgrade() -> None:
    op.drop_column("knowledge_docs", "stack")
    op.drop_column("knowledge_docs", "verified_at")
    op.drop_column("knowledge_docs", "status")
