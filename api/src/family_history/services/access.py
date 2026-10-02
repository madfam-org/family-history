"""Request-scoped database sessions, membership checks and role gates.

Defence in depth: the application checks membership and role first, then sets the RLS scope
(`app.user_sub`, `app.family_space_id`) so the database enforces the same boundary even if a
query forgets a `WHERE family_space_id = ...`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_history.auth import EarlyAccessPrincipal, Principal
from family_history.db.engine import Database, set_scope
from family_history.errors import APIError, forbidden, not_found
from family_history.models import SpaceMember
from family_history.models.enums import ROLE_RANK, Role


def get_database(request: Request) -> Database:
    database = getattr(request.app.state, "database", None)
    if not isinstance(database, Database):
        raise APIError(503, "database_unavailable", "The database is not configured.")
    return database


def get_db(database: Annotated[Database, Depends(get_database)]) -> Iterator[Session]:
    """One session per request. Writes commit explicitly; anything uncommitted rolls back."""
    session = database.sessions()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class SpaceContext:
    """The caller inside one family space, with the RLS scope already set."""

    db: Session
    principal: Principal
    space_id: uuid.UUID
    role: Role

    @property
    def sub(self) -> str:
        return self.principal.sub

    def can(self, minimum: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]

    def require(self, minimum: Role) -> None:
        if not self.can(minimum):
            raise forbidden(
                "insufficient_role", f"This action needs the {minimum.value} role or higher."
            )


def user_scoped(db: Session, principal: Principal) -> Session:
    set_scope(db, user_sub=principal.sub, space_id=None)
    return db


def enter_space(db: Session, principal: Principal, space_id: uuid.UUID) -> SpaceContext:
    """Check membership (404 when absent, so existence never leaks), then scope RLS to it."""
    set_scope(db, user_sub=principal.sub, space_id=None)
    role = db.scalar(
        select(SpaceMember.role).where(
            SpaceMember.family_space_id == space_id, SpaceMember.user_sub == principal.sub
        )
    )
    if role is None:
        raise not_found("space_not_found", "Family space not found.")
    set_scope(db, user_sub=principal.sub, space_id=space_id)
    return SpaceContext(db=db, principal=principal, space_id=space_id, role=Role(role))


def get_user_db(principal: EarlyAccessPrincipal, db: DbSession) -> Session:
    return user_scoped(db, principal)


def get_space_context(
    space_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> SpaceContext:
    return enter_space(db, principal, space_id)


UserDb = Annotated[Session, Depends(get_user_db)]
SpaceCtx = Annotated[SpaceContext, Depends(get_space_context)]
