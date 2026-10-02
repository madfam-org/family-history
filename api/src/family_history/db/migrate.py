"""Alembic helpers: run migrations and compare the database with the code's head."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config(database_url: str | None = None) -> Config:
    """Config pointing at the migrations shipped inside the package (no alembic.ini needed)."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


@lru_cache(maxsize=1)
def head_revisions() -> frozenset[str]:
    return frozenset(ScriptDirectory.from_config(alembic_config()).get_heads())


def current_revisions(connection: Connection) -> frozenset[str]:
    return frozenset(MigrationContext.configure(connection).get_current_heads())


def is_at_head(connection: Connection) -> bool:
    return current_revisions(connection) == head_revisions()


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def downgrade_to_base(database_url: str) -> None:
    command.downgrade(alembic_config(database_url), "base")
