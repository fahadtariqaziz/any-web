"""One SQLAlchemy engine for the app's own tables.

DATABASE_URL stays "postgresql://..." because PostgresSaver (checkpointing.py) needs that form.
SQLAlchemy needs to be told which driver to use, so we turn it into "postgresql+psycopg://..."
(psycopg 3, the same driver the checkpointer uses).
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from ai_decision_arena.config import get_settings


def sqlalchemy_url(database_url: str | None = None) -> str:
    url = database_url or get_settings().database_url
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    raise ValueError("DATABASE_URL must start with postgresql://")


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: test a pooled connection before using it (Postgres may have restarted meanwhile).
    return create_engine(sqlalchemy_url(), pool_pre_ping=True)


def session_factory() -> sessionmaker:
    """Usage:  with session_factory().begin() as db: ...   (commits at the end, rolls back on error)."""
    return sessionmaker(get_engine(), expire_on_commit=False)
