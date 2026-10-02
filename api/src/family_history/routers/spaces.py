"""The caller (`/v1/me`), family spaces and their members."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from family_history.auth import AuthenticatedPrincipal, EarlyAccessPrincipal, has_early_access
from family_history.config import AppSettings
from family_history.db.engine import set_scope
from family_history.errors import ERROR_RESPONSES, not_found
from family_history.models import FamilySpace, Person, SpaceMember
from family_history.models.enums import RevisionAction, Role
from family_history.routers.schemas.spaces import (
    Me,
    Member,
    Space,
    SpaceCreate,
    SpaceRename,
    SpaceSummary,
)
from family_history.services import audit
from family_history.services.access import (
    DbSession,
    SpaceContext,
    SpaceCtx,
    get_database,
    user_scoped,
)
from family_history.services.privacy import visible_people

router = APIRouter(prefix="/v1", tags=["spaces"], responses=ERROR_RESPONSES)


def _summaries(db: Session, sub: str) -> list[SpaceSummary]:
    rows = db.execute(
        select(FamilySpace.id, FamilySpace.name, SpaceMember.role)
        .join(SpaceMember, SpaceMember.family_space_id == FamilySpace.id)
        .where(SpaceMember.user_sub == sub)
        .order_by(FamilySpace.name, FamilySpace.id)
    ).all()
    ids = [row.id for row in rows]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        counts = {
            space_id: count
            for space_id, count in db.execute(
                select(Person.family_space_id, func.count())
                .where(Person.family_space_id.in_(ids), visible_people(sub))
                .group_by(Person.family_space_id)
            ).tuples()
        }
    return [
        SpaceSummary(
            id=row.id, name=row.name, role=Role(row.role), people_count=counts.get(row.id, 0)
        )
        for row in rows
    ]


def _space_out(ctx: SpaceContext) -> Space:
    space = ctx.db.get(FamilySpace, ctx.space_id)
    if space is None:
        raise not_found("space_not_found", "Family space not found.")
    count = ctx.db.scalar(
        select(func.count())
        .select_from(Person)
        .where(Person.family_space_id == ctx.space_id, visible_people(ctx.sub))
    )
    return Space(
        id=space.id,
        name=space.name,
        role=ctx.role,
        people_count=int(count or 0),
        janua_organization_id=space.janua_organization_id,
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


@router.get("/me", response_model=Me)
def me(
    request: Request,
    principal: AuthenticatedPrincipal,
    settings: AppSettings,
) -> Me:
    """The caller. Reachable without early access, so the app can show the waitlist state."""
    early = has_early_access(principal, settings)
    spaces: list[SpaceSummary] = []
    if early:
        database = get_database(request)
        with database.sessions() as db:
            spaces = _summaries(user_scoped(db, principal), principal.sub)
    return Me(
        sub=principal.sub,
        email=principal.email,
        name=principal.name,
        early_access=early,
        spaces=spaces,
    )


@router.get("/spaces", response_model=list[SpaceSummary])
def list_spaces(principal: EarlyAccessPrincipal, db: DbSession) -> list[SpaceSummary]:
    return _summaries(user_scoped(db, principal), principal.sub)


@router.post("/spaces", response_model=Space, status_code=status.HTTP_201_CREATED)
def create_space(body: SpaceCreate, principal: EarlyAccessPrincipal, db: DbSession) -> Space:
    """Create a family space. The creator becomes its steward."""
    user_scoped(db, principal)
    space = FamilySpace(id=uuid.uuid4(), name=body.name, created_by=principal.sub)
    db.add(space)
    db.flush()
    set_scope(db, user_sub=principal.sub, space_id=space.id)
    db.add(SpaceMember(family_space_id=space.id, user_sub=principal.sub, role=Role.STEWARD.value))
    db.flush()
    ctx = SpaceContext(db=db, principal=principal, space_id=space.id, role=Role.STEWARD)
    audit.record(ctx, "family_space", space.id, RevisionAction.CREATE, {"name": body.name})
    db.commit()
    return _space_out(ctx)


@router.get("/spaces/{space_id}", response_model=Space)
def get_space(ctx: SpaceCtx) -> Space:
    return _space_out(ctx)


@router.patch("/spaces/{space_id}", response_model=Space)
def rename_space(body: SpaceRename, ctx: SpaceCtx) -> Space:
    ctx.require(Role.STEWARD)
    space = ctx.db.get(FamilySpace, ctx.space_id)
    if space is None:
        raise not_found("space_not_found", "Family space not found.")
    diff = audit.changes({"name": space.name}, {"name": body.name})
    if diff:
        space.name = body.name
        audit.record(ctx, "family_space", space.id, RevisionAction.UPDATE, diff)
        ctx.db.commit()
    return _space_out(ctx)


@router.get("/spaces/{space_id}/members", response_model=list[Member])
def list_members(ctx: SpaceCtx) -> list[Member]:
    rows = ctx.db.scalars(
        select(SpaceMember)
        .where(SpaceMember.family_space_id == ctx.space_id)
        .order_by(SpaceMember.created_at, SpaceMember.user_sub)
    ).all()
    return [Member(user_sub=r.user_sub, role=Role(r.role), created_at=r.created_at) for r in rows]
