"""M2: research domains (evidence_records.perspective and knowledge_docs.perspective -> domain).

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-10-24

Pure column renames. Old rows keep their old values (research / doctor / patient) from health-era sessions.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("evidence_records", "perspective", new_column_name="domain")
    op.alter_column("knowledge_docs", "perspective", new_column_name="domain")


def downgrade() -> None:
    op.alter_column("knowledge_docs", "domain", new_column_name="perspective")
    op.alter_column("evidence_records", "domain", new_column_name="perspective")
