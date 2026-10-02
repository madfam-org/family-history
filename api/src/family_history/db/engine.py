"""Engine, session factory and per-transaction row-level-security settings.

Row-level security policies (see the initial migration) read two transaction-local settings:

- `app.user_sub`: the Janua subject of the caller;
- `app.family_space_id`: the family space the request works in, set only after the application
  has checked the caller's membership.

`set_config(..., is_local => true)` scopes them to the current transaction, so they never leak
across pooled connections. The values live in `Session.info` and an `after_begin` hook re-applies
them to every transaction the session opens, including the one that follows a commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

SCOPE_USER_KEY = "fh_user_sub"
SCOPE_SPACE_KEY = "fh_family_space_id"

_SET_SCOPE_SQL = text(
    "SELECT set_config('app.user_sub', :user_sub, true), "
    "set_config('app.family_space_id', :space_id, true)"
)


def normalize_database_url(url: str) -> str:
    """Use the psycopg 3 driver whatever scheme the platform hands us."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _scope_params(session: Session) -> dict[str, str]:
    user_sub = session.info.get(SCOPE_USER_KEY)
    space_id = session.info.get(SCOPE_SPACE_KEY)
    return {
        "user_sub": user_sub if isinstance(user_sub, str) else "",
        "space_id": str(space_id) if isinstance(space_id, uuid.UUID) else "",
    }


def _apply_scope_on_begin(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    connection.execute(_SET_SCOPE_SQL, _scope_params(session))


def set_scope(
    session: Session, *, user_sub: str | None, space_id: uuid.UUID | None = None
) -> None:
    """Record the RLS scope on the session and apply it to the open transaction, if any."""
    session.info[SCOPE_USER_KEY] = user_sub
    session.info[SCOPE_SPACE_KEY] = space_id
    if session.in_transaction():
        session.execute(_SET_SCOPE_SQL, _scope_params(session))


def scope_of(session: Session) -> tuple[str | None, uuid.UUID | None]:
    user_sub = session.info.get(SCOPE_USER_KEY)
    space_id = session.info.get(SCOPE_SPACE_KEY)
    return (
        user_sub if isinstance(user_sub, str) else None,
        space_id if isinstance(space_id, uuid.UUID) else None,
    )


@dataclass
class Database:
    engine: Engine
    sessions: sessionmaker[Session]

    def dispose(self) -> None:
        self.engine.dispose()


def create_database(url: str, **engine_kwargs: Any) -> Database:
    options: dict[str, Any] = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}
    options.update(engine_kwargs)
    engine = create_engine(normalize_database_url(url), **options)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
    event.listen(sessions, "after_begin", _apply_scope_on_begin)
    return Database(engine=engine, sessions=sessions)
