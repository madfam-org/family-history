"""Alembic environment: online migrations against DIRECT_DATABASE_URL."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

from family_history.db.engine import normalize_database_url
from family_history.models import Base

config = context.config
target_metadata = Base.metadata

# Trigram search indexes exist only where pg_trgm is installable (see 0002); the models do
# not declare them, so autogenerate must not propose dropping them.
OPTIONAL_INDEXES = frozenset({"ix_person_search_trgm", "ix_place_search_trgm"})


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "index" and reflected and name in OPTIONAL_INDEXES)


def _database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("DIRECT_DATABASE_URL")
    if not url:
        raise RuntimeError("DIRECT_DATABASE_URL is not set")
    return normalize_database_url(str(url))


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
