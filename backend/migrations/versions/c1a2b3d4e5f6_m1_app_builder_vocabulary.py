"""M1: app-builder vocabulary (health columns renamed, patient_memories -> user_memories).

Revision ID: c1a2b3d4e5f6
Revises: 9996b6ffc969
Create Date: 2026-10-24

Pure renames: no data is lost, downgrade restores the old names.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9996b6ffc969"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("decision_sessions", "condition_name", new_column_name="project_name")
    op.alter_column("decision_sessions", "condition_category", new_column_name="project_category")
    op.alter_column("decision_sessions", "red_flags", new_column_name="risk_flags")
    op.alter_column("decision_sessions", "patient_id", new_column_name="user_id")
    op.execute("ALTER INDEX ix_decision_sessions_patient_id RENAME TO ix_decision_sessions_user_id")

    op.rename_table("patient_memories", "user_memories")
    op.alter_column("user_memories", "patient_id", new_column_name="user_id")
    op.execute("ALTER INDEX ix_patient_memories_patient_id RENAME TO ix_user_memories_user_id")
    op.execute("ALTER TABLE user_memories RENAME CONSTRAINT uq_patient_memories_fact TO uq_user_memories_fact")
    op.execute("ALTER TABLE user_memories RENAME CONSTRAINT patient_memories_pkey TO user_memories_pkey")
    op.execute("ALTER SEQUENCE patient_memories_id_seq RENAME TO user_memories_id_seq")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE user_memories_id_seq RENAME TO patient_memories_id_seq")
    op.execute("ALTER TABLE user_memories RENAME CONSTRAINT user_memories_pkey TO patient_memories_pkey")
    op.execute("ALTER TABLE user_memories RENAME CONSTRAINT uq_user_memories_fact TO uq_patient_memories_fact")
    op.execute("ALTER INDEX ix_user_memories_user_id RENAME TO ix_patient_memories_patient_id")
    op.alter_column("user_memories", "user_id", new_column_name="patient_id")
    op.rename_table("user_memories", "patient_memories")

    op.execute("ALTER INDEX ix_decision_sessions_user_id RENAME TO ix_decision_sessions_patient_id")
    op.alter_column("decision_sessions", "user_id", new_column_name="patient_id")
    op.alter_column("decision_sessions", "risk_flags", new_column_name="red_flags")
    op.alter_column("decision_sessions", "project_category", new_column_name="condition_category")
    op.alter_column("decision_sessions", "project_name", new_column_name="condition_name")
