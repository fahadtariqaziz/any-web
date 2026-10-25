"""M11 part 4: knowledge_docs.condition -> topic (the last health-app column name).

Postgres rewrites the generated search_vector expression itself when the column is renamed.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-10-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("knowledge_docs", "condition", new_column_name="topic")


def downgrade() -> None:
    op.alter_column("knowledge_docs", "topic", new_column_name="condition")
