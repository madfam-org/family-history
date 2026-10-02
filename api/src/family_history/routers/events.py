"""Events with participants: create, update and delete."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, not_found
from family_history.models import Event, EventParticipant
from family_history.models.base import utcnow
from family_history.models.enums import RevisionAction, Role
from family_history.routers.schemas.events import Event as EventOut
from family_history.routers.schemas.events import EventCreate, EventPatch
from family_history.services import audit
from family_history.services.access import (
    DbSession,
    SpaceContext,
    SpaceCtx,
    enter_space,
    user_scoped,
)
from family_history.services.events import (
    event_snapshot,
    events_out,
    recompute_living,
    replace_participants,
    require_place,
)
from family_history.services.privacy import default_sensitivity

router = APIRouter(prefix="/v1", tags=["events"], responses=ERROR_RESPONSES)


def _participants_snapshot(ctx: SpaceContext, event_id: uuid.UUID) -> list[dict[str, str]]:
    rows = ctx.db.scalars(
        select(EventParticipant)
        .where(EventParticipant.event_id == event_id)
        .order_by(EventParticipant.role, EventParticipant.person_id)
    ).all()
    return [{"person_id": str(r.person_id), "role": r.role} for r in rows]


def _visible_event(
    db: DbSession, principal: EarlyAccessPrincipal, event_id: uuid.UUID
) -> tuple[SpaceContext, Event]:
    user_scoped(db, principal)
    space_id = db.scalar(select(Event.family_space_id).where(Event.id == event_id))
    if space_id is None:
        raise not_found("event_not_found", "Event not found.")
    ctx = enter_space(db, principal, space_id)
    event = db.get(Event, event_id)
    if event is None or not events_out(ctx, [event]):
        raise not_found("event_not_found", "Event not found.")
    return ctx, event


def _single(ctx: SpaceContext, event: Event) -> EventOut:
    rendered = events_out(ctx, [event])
    if not rendered:
        raise not_found("event_not_found", "Event not found.")
    return rendered[0]


@router.post(
    "/spaces/{space_id}/events", response_model=EventOut, status_code=status.HTTP_201_CREATED
)
def create_event(body: EventCreate, ctx: SpaceCtx) -> EventOut:
    """Sacraments default to the `religion` sensitivity and medical events to `health`."""
    ctx.require(Role.CONTRIBUTOR)
    require_place(ctx, body.place_id)
    sensitivity = body.sensitivity or default_sensitivity(body.type)
    event = Event(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        type=body.type,
        date_value=body.date_value,
        place_id=body.place_id,
        description=body.description,
        sensitivity=sensitivity.value if sensitivity else None,
        created_by=ctx.sub,
    )
    ctx.db.add(event)
    ctx.db.flush()
    touched = replace_participants(ctx, event, body.participants)
    recompute_living(ctx, touched)
    audit.record(
        ctx,
        "event",
        event.id,
        RevisionAction.CREATE,
        {**event_snapshot(event), "participants": _participants_snapshot(ctx, event.id)},
    )
    ctx.db.commit()
    return _single(ctx, event)


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: uuid.UUID, body: EventPatch, principal: EarlyAccessPrincipal, db: DbSession
) -> EventOut:
    ctx, event = _visible_event(db, principal, event_id)
    ctx.require(Role.EDITOR)
    before_participants = _participants_snapshot(ctx, event.id)
    before = {**event_snapshot(event), "participants": before_participants}
    fields = body.model_fields_set
    if "type" in fields and body.type is not None:
        event.type = body.type
    if "date_value" in fields:
        event.date_value = body.date_value
        # The bounds belong to the old value; the domain library recomputes them.
        event.date_earliest = None
        event.date_latest = None
    if "place_id" in fields:
        require_place(ctx, body.place_id)
        event.place_id = body.place_id
    if "description" in fields:
        event.description = body.description
    if "sensitivity" in fields:
        event.sensitivity = body.sensitivity.value if body.sensitivity else None
    touched: set[uuid.UUID] = {uuid.UUID(p["person_id"]) for p in before_participants}
    if body.participants is not None:
        touched |= replace_participants(ctx, event, body.participants)
    ctx.db.flush()
    after = {**event_snapshot(event), "participants": _participants_snapshot(ctx, event.id)}
    diff = audit.changes(before, after)
    if diff:
        event.updated_at = utcnow()
        audit.record(ctx, "event", event.id, RevisionAction.UPDATE, diff)
    recompute_living(ctx, touched)
    ctx.db.commit()
    return _single(ctx, event)


@router.delete(
    "/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_event(event_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession) -> Response:
    ctx, event = _visible_event(db, principal, event_id)
    ctx.require(Role.EDITOR)
    participants = _participants_snapshot(ctx, event.id)
    audit.record(
        ctx,
        "event",
        event.id,
        RevisionAction.DELETE,
        {**event_snapshot(event), "participants": participants},
    )
    db.delete(event)
    db.flush()
    recompute_living(ctx, [uuid.UUID(p["person_id"]) for p in participants])
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
