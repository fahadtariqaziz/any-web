"""Alembic environment: how migrations connect and which tables they manage.

Run from backend/:
    uv run alembic revision --autogenerate -m "what changed"   # compare models.py with the DB, write a migration
    uv run alembic upgrade head                                 # apply all migrations
    uv run alembic downgrade -1                                 # undo the last one

Two project-specific choices:
- The URL comes from DATABASE_URL (.env) via db/engine.py, not from alembic.ini.
- LangGraph's checkpoint tables live in the same database but are NOT ours (PostgresSaver.setup() manages
  them). Without the filter below, autogenerate sees tables with no model and proposes DROPPING them.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from ai_decision_arena.db.engine import sqlalchemy_url
from ai_decision_arena.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

LANGGRAPH_TABLES = {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}


def include_object(obj, name, type_, reflected, compare_to):
    """Ignore LangGraph's tables (and their indexes) so Alembic never creates, alters or drops them."""
    if type_ == "table" and name in LANGGRAPH_TABLES:
        return False
    if type_ in ("index", "unique_constraint", "foreign_key_constraint") and getattr(obj, "table", None) is not None:
        return obj.table.name not in LANGGRAPH_TABLES
    return True


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=sqlalchemy_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
