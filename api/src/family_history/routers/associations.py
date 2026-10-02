"""Associations: someone's part in another person's event (padrinos, witnesses, officiants)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, conflict, not_found, unprocessable
from family_history.models import Association, Event, EventParticipant
from family_history.models.enums import ParticipantRole, RevisionAction, Role
from family_history.routers.schemas.kinship import Association as AssociationOut
from family_history.routers.schemas.kinship import AssociationCreate
from family_history.services import audit
from family_history.services.access import DbSession, SpaceCtx, enter_space, user_scoped
from family_history.services.events import events_out, require_people

router = APIRouter(prefix="/v1", tags=["associations"], responses=ERROR_RESPONSES)


def _out(row: Association) -> AssociationOut:
    return AssociationOut.model_validate(
        {
            "id": row.id,
            "space_id": row.family_space_id,
            "event_id": row.event_id,
            "person_id": row.person_id,
            "role": row.role,
            "phrase": row.phrase,
            "created_at": row.created_at,
        }
    )


@router.post(
    "/spaces/{space_id}/associations",
    response_model=AssociationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_association(body: AssociationCreate, ctx: SpaceCtx) -> AssociationOut:
    """`422 unknown_event` / `unknown_person` for anything the caller cannot see in the space;
    `422 association_is_principal` when the person is the event's principal (nobody is their own
    padrino); `409 association_exists` for a repeat."""
    ctx.require(Role.CONTRIBUTOR)
    event = ctx.db.scalar(
        select(Event).where(Event.family_space_id == ctx.space_id, Event.id == body.event_id)
    )
    if event is None or not events_out(ctx, [event]):
        raise unprocessable("unknown_event", "The event does not exist in this space.")
    require_people(ctx, [body.person_id])
    principal = ctx.db.scalar(
        select(EventParticipant.id).where(
            EventParticipant.event_id == event.id,
            EventParticipant.person_id == body.person_id,
            EventParticipant.role == ParticipantRole.PRINCIPAL.value,
        )
    )
    if principal is not None:
        raise unprocessable(
            "association_is_principal", "The event's principal cannot be associated with it."
        )
    duplicate = ctx.db.scalar(
        select(Association.id).where(
            Association.event_id == event.id,
            Association.person_id == body.person_id,
            Association.role == body.role.value,
        )
    )
    if duplicate is not None:
        raise conflict("association_exists", "This association already exists.")
    row = Association(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        event_id=event.id,
        person_id=body.person_id,
        role=body.role.value,
        phrase=body.phrase,
        created_by=ctx.sub,
    )
    ctx.db.add(row)
    audit.record(ctx, "association", row.id, RevisionAction.CREATE, body.model_dump(mode="json"))
    ctx.db.commit()
    return _out(row)


@router.delete(
    "/associations/{association_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_association(
    association_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> Response:
    user_scoped(db, principal)
    space_id = db.scalar(
        select(Association.family_space_id).where(Association.id == association_id)
    )
    if space_id is None:
        raise not_found("association_not_found", "Association not found.")
    ctx = enter_space(db, principal, space_id)
    row = db.get(Association, association_id)
    event = db.get(Event, row.event_id) if row is not None else None
    if row is None or event is None or not events_out(ctx, [event]):
        raise not_found("association_not_found", "Association not found.")
    ctx.require(Role.EDITOR)
    audit.record(
        ctx,
        "association",
        row.id,
        RevisionAction.DELETE,
        {
            "event_id": row.event_id,
            "person_id": row.person_id,
            "role": row.role,
            "phrase": row.phrase,
        },
    )
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
