"""Living status through `family_history.domain.living`, kept current on every write.

`recompute_living` runs after any write that touches a person's events, participants or the
citations behind them. It feeds `assess_living` every event where the person is the principal,
with today's date in America/Mexico_City.

Death evidence (PRIVACY.md §1): a death, burial or cremation event counts only when a current
assertion about that event carries at least one citation and is neither retracted nor disputed.
A death nobody has cited leaves the person treated as living.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from family_history.domain.events import EventType
from family_history.domain.living import (
    LivingStatus,
    VitalEvent,
    assess_living,
    is_private_by_default,
)
from family_history.models import Assertion, Event, EventParticipant, Person
from family_history.models.enums import (
    AssertionStatus,
    ParticipantRole,
    RevisionAction,
    SubjectType,
    Visibility,
)
from family_history.services import audit
from family_history.services.access import SpaceContext
from family_history.services.dates import stored_value
from family_history.services.evidence import current_assertions

EVIDENCE_STATUSES = (AssertionStatus.SUGGESTED.value, AssertionStatus.ACCEPTED.value)


def _mexico_city() -> tzinfo:
    try:
        return ZoneInfo("America/Mexico_City")
    except ZoneInfoNotFoundError:
        # Without tz data: Mexico City has kept UTC−06:00 all year since daylight saving time
        # was abolished in October 2022, so the fixed offset gives the same date.
        return timezone(timedelta(hours=-6), "America/Mexico_City")


MEXICO_CITY = _mexico_city()


def today_mexico_city(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(MEXICO_CITY).date()


def is_private(living_status: str, visibility: str) -> bool:
    """Private by default (living or unknown), or marked private by its creator."""
    if visibility == Visibility.PRIVATE.value:
        return True
    try:
        return is_private_by_default(LivingStatus(living_status))
    except ValueError:
        return True


def evidenced_events(ctx: SpaceContext, event_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Events backed by a current, cited assertion that is neither retracted nor disputed."""
    wanted = list(dict.fromkeys(event_ids))
    if not wanted:
        return set()
    rows = ctx.db.scalars(
        current_assertions()
        .with_only_columns(Assertion.subject_id)
        .where(
            Assertion.family_space_id == ctx.space_id,
            Assertion.subject_type == SubjectType.EVENT.value,
            Assertion.subject_id.in_(wanted),
            Assertion.status.in_(EVIDENCE_STATUSES),
            func.cardinality(Assertion.citation_ids) > 0,
        )
    ).all()
    return set(rows)


def principals_of(ctx: SpaceContext, event_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    wanted = list(dict.fromkeys(event_ids))
    if not wanted:
        return set()
    return set(
        ctx.db.scalars(
            select(EventParticipant.person_id).where(
                EventParticipant.event_id.in_(wanted),
                EventParticipant.role == ParticipantRole.PRINCIPAL.value,
            )
        ).all()
    )


def _vital_events(ctx: SpaceContext, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[VitalEvent]]:
    rows = ctx.db.execute(
        select(EventParticipant.person_id, Event.id, Event.type, Event.date_value)
        .join(Event, Event.id == EventParticipant.event_id)
        .where(
            EventParticipant.person_id.in_(ids),
            EventParticipant.role == ParticipantRole.PRINCIPAL.value,
        )
    ).all()
    death_ids = [event_id for _, event_id, kind, _ in rows if EventType(kind).is_death_evidence]
    evidenced = evidenced_events(ctx, death_ids)
    events: dict[uuid.UUID, list[VitalEvent]] = defaultdict(list)
    for person_id, event_id, kind, date_value in rows:
        evidence = event_id in evidenced
        events[person_id].append(VitalEvent(EventType(kind), stored_value(date_value), evidence))
    return events


def recompute_living(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> None:
    """Re-derive `living_status` for these people; a person who may be living loses public
    visibility. Each change is recorded in `revision`."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return
    ctx.db.flush()
    people = ctx.db.scalars(
        select(Person).where(Person.family_space_id == ctx.space_id, Person.id.in_(wanted))
    ).all()
    events = _vital_events(ctx, wanted)
    today = today_mexico_city()
    for person in people:
        status = assess_living(events.get(person.id, []), today=today).status
        before = {"living_status": person.living_status, "visibility": person.visibility}
        person.living_status = status.value
        if is_private_by_default(status) and person.visibility == Visibility.PUBLIC_MEMORIAL.value:
            person.visibility = Visibility.SPACE.value
        after = {"living_status": person.living_status, "visibility": person.visibility}
        diff = audit.changes(before, after)
        if diff:
            audit.record(ctx, "person", person.id, RevisionAction.UPDATE, diff)


def recompute_for_subject(ctx: SpaceContext, subject_type: str, subject_id: uuid.UUID) -> None:
    """After an assertion write: citations on an event change its principals' evidence."""
    if subject_type == SubjectType.EVENT.value:
        recompute_living(ctx, principals_of(ctx, [subject_id]))
    elif subject_type == SubjectType.PERSON.value:
        recompute_living(ctx, [subject_id])
