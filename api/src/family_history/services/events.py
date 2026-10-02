"""Event reads with privacy filtering, participant validation and living-status upkeep."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select

from family_history.errors import unprocessable
from family_history.models import Event, EventParticipant, Person, Place
from family_history.models.enums import ParticipantRole, RevisionAction, Sensitivity, Visibility
from family_history.routers.schemas.events import Event as EventOut
from family_history.routers.schemas.events import Participant, ParticipantIn
from family_history.services import audit
from family_history.services.access import SpaceContext
from family_history.services.privacy import (
    LifeEvent,
    compute_living_status,
    sensitive_visible,
    treated_as_living,
    visible_people,
)


def require_people(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Person]:
    """Load people the caller can see in this space; 422 if any id is unknown or hidden."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    rows = ctx.db.scalars(
        select(Person).where(
            Person.family_space_id == ctx.space_id,
            Person.id.in_(wanted),
            visible_people(ctx.sub),
        )
    ).all()
    found = {person.id: person for person in rows}
    if len(found) != len(wanted):
        raise unprocessable("unknown_person", "A referenced person does not exist in this space.")
    return found


def require_place(ctx: SpaceContext, place_id: uuid.UUID | None) -> Place | None:
    if place_id is None:
        return None
    place = ctx.db.scalar(
        select(Place).where(Place.family_space_id == ctx.space_id, Place.id == place_id)
    )
    if place is None:
        raise unprocessable("unknown_place", "The place does not exist in this space.")
    return place


def replace_participants(
    ctx: SpaceContext, event: Event, participants: Sequence[ParticipantIn]
) -> set[uuid.UUID]:
    """Set the event's participants; returns every person id touched (old and new)."""
    require_people(ctx, (p.person_id for p in participants))
    pairs = list(dict.fromkeys((p.person_id, p.role.value) for p in participants))
    existing = ctx.db.scalars(
        select(EventParticipant).where(EventParticipant.event_id == event.id)
    ).all()
    touched = {row.person_id for row in existing}
    for row in existing:
        ctx.db.delete(row)
    ctx.db.flush()
    for person_id, role in pairs:
        ctx.db.add(
            EventParticipant(
                family_space_id=ctx.space_id, event_id=event.id, person_id=person_id, role=role
            )
        )
        touched.add(person_id)
    return touched


def recompute_living(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> None:
    """Re-derive `living_status` for these people from their principal events."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return
    ctx.db.flush()
    people = ctx.db.scalars(
        select(Person).where(Person.family_space_id == ctx.space_id, Person.id.in_(wanted))
    ).all()
    rows = ctx.db.execute(
        select(EventParticipant.person_id, Event.type, Event.date_latest)
        .join(Event, Event.id == EventParticipant.event_id)
        .where(
            EventParticipant.person_id.in_(wanted),
            EventParticipant.role == ParticipantRole.PRINCIPAL.value,
        )
    ).all()
    events: dict[uuid.UUID, list[LifeEvent]] = defaultdict(list)
    for person_id, event_type, date_latest in rows:
        events[person_id].append(LifeEvent(type=event_type, date_latest=date_latest))
    today = datetime.now(UTC).date()
    for person in people:
        status = compute_living_status(events.get(person.id, []), today).value
        before = {"living_status": person.living_status, "visibility": person.visibility}
        person.living_status = status
        # Nothing about a living person is ever public.
        if treated_as_living(status) and person.visibility == Visibility.PUBLIC_MEMORIAL.value:
            person.visibility = Visibility.SPACE.value
        after = {"living_status": person.living_status, "visibility": person.visibility}
        diff = audit.changes(before, after)
        if diff:
            audit.record(ctx, "person", person.id, RevisionAction.UPDATE, diff)


def _living_by_person(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, bool]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    rows = ctx.db.execute(
        select(Person.id, Person.living_status).where(Person.id.in_(wanted))
    ).all()
    return {person_id: treated_as_living(status) for person_id, status in rows}


def visible_person_ids(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return set()
    return set(
        ctx.db.scalars(
            select(Person.id).where(Person.id.in_(wanted), visible_people(ctx.sub))
        ).all()
    )


def events_out(ctx: SpaceContext, events: Sequence[Event]) -> list[EventOut]:
    """Serialize events the caller may see, hiding hidden participants and sensitive events
    about living people recorded by someone else."""
    if not events:
        return []
    event_ids = [event.id for event in events]
    participants = ctx.db.scalars(
        select(EventParticipant)
        .where(EventParticipant.event_id.in_(event_ids))
        .order_by(EventParticipant.role, EventParticipant.person_id)
    ).all()
    by_event: dict[uuid.UUID, list[EventParticipant]] = defaultdict(list)
    for row in participants:
        by_event[row.event_id].append(row)
    all_people = [row.person_id for row in participants]
    visible = visible_person_ids(ctx, all_people)
    living = _living_by_person(ctx, all_people)
    place_ids = [event.place_id for event in events if event.place_id is not None]
    places: dict[uuid.UUID, str] = {}
    if place_ids:
        places = {
            place_id: name
            for place_id, name in ctx.db.execute(
                select(Place.id, Place.name).where(Place.id.in_(place_ids))
            ).tuples()
        }

    out: list[EventOut] = []
    for event in events:
        rows = by_event.get(event.id, [])
        about_living = any(
            living.get(row.person_id, True)
            for row in rows
            if row.role == ParticipantRole.PRINCIPAL.value
        )
        if not sensitive_visible(event.sensitivity, event.created_by, ctx.sub, about_living):
            continue
        out.append(
            EventOut(
                id=event.id,
                space_id=event.family_space_id,
                type=event.type,
                date_value=event.date_value,
                date_earliest=event.date_earliest,
                date_latest=event.date_latest,
                place_id=event.place_id,
                place=places.get(event.place_id) if event.place_id else None,
                description=event.description,
                sensitivity=Sensitivity(event.sensitivity) if event.sensitivity else None,
                participants=[
                    Participant(person_id=row.person_id, role=ParticipantRole(row.role))
                    for row in rows
                    if row.person_id in visible
                ],
                created_by=event.created_by,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
        )
    return out


def event_snapshot(event: Event) -> dict[str, object]:
    return {
        "type": event.type,
        "date_value": event.date_value,
        "place_id": event.place_id,
        "description": event.description,
        "sensitivity": event.sensitivity,
    }
