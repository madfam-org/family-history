"""Assertions (append-only, with provenance) and their citations."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import Select, exists, select
from sqlalchemy.orm import aliased

from family_history.errors import conflict, not_found, unprocessable
from family_history.models import (
    Assertion,
    Citation,
    Event,
    EventParticipant,
    Person,
    Place,
    Relationship,
)
from family_history.models.enums import (
    AssertionStatus,
    ParticipantRole,
    RevisionAction,
    Sensitivity,
    SubjectType,
)
from family_history.routers.schemas.evidence import Assertion as AssertionOut
from family_history.routers.schemas.evidence import Citation as CitationOut
from family_history.services import audit
from family_history.services.access import SpaceContext
from family_history.services.privacy import sensitive_visible, treated_as_living, visible_people


def current_assertions() -> Select[tuple[Assertion]]:
    """Assertions that no later row supersedes (the head of each chain)."""
    newer = aliased(Assertion)
    return select(Assertion).where(~exists().where(newer.supersedes_id == Assertion.id))


def require_citations(ctx: SpaceContext, ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []
    found = set(
        ctx.db.scalars(
            select(Citation.id).where(
                Citation.family_space_id == ctx.space_id, Citation.id.in_(wanted)
            )
        ).all()
    )
    if found != set(wanted):
        raise unprocessable("unknown_citation", "A referenced citation does not exist.")
    return wanted


def _principals_living(ctx: SpaceContext, event_ids: Iterable[uuid.UUID]) -> bool:
    ids = list(event_ids)
    if not ids:
        return False
    statuses = ctx.db.scalars(
        select(Person.living_status)
        .join(EventParticipant, EventParticipant.person_id == Person.id)
        .where(
            EventParticipant.event_id.in_(ids),
            EventParticipant.role == ParticipantRole.PRINCIPAL.value,
        )
    ).all()
    return any(treated_as_living(status) for status in statuses)


def subject_about_living(ctx: SpaceContext, subject_type: str, subject_id: uuid.UUID) -> bool:
    if subject_type == SubjectType.PERSON.value:
        status = ctx.db.scalar(select(Person.living_status).where(Person.id == subject_id))
        return status is None or treated_as_living(status)
    if subject_type == SubjectType.EVENT.value:
        return _principals_living(ctx, [subject_id])
    if subject_type == SubjectType.RELATIONSHIP.value:
        rel = ctx.db.get(Relationship, subject_id)
        if rel is None:
            return True
        statuses = ctx.db.scalars(
            select(Person.living_status).where(
                Person.id.in_([rel.from_person_id, rel.to_person_id])
            )
        ).all()
        return any(treated_as_living(status) for status in statuses)
    return False


def require_subject(ctx: SpaceContext, subject_type: SubjectType, subject_id: uuid.UUID) -> None:
    """The subject must exist in this space (and, for people, be visible to the caller)."""
    query: Select[tuple[uuid.UUID]]
    if subject_type is SubjectType.PERSON:
        query = select(Person.id).where(
            Person.family_space_id == ctx.space_id,
            Person.id == subject_id,
            visible_people(ctx.sub),
        )
    elif subject_type is SubjectType.EVENT:
        query = select(Event.id).where(
            Event.family_space_id == ctx.space_id, Event.id == subject_id
        )
    elif subject_type is SubjectType.RELATIONSHIP:
        query = select(Relationship.id).where(
            Relationship.family_space_id == ctx.space_id, Relationship.id == subject_id
        )
    else:
        query = select(Place.id).where(
            Place.family_space_id == ctx.space_id, Place.id == subject_id
        )
    if ctx.db.scalar(query) is None:
        raise unprocessable("unknown_subject", "The assertion subject does not exist.")


def to_out(assertion: Assertion) -> AssertionOut:
    return AssertionOut(
        id=assertion.id,
        space_id=assertion.family_space_id,
        subject_type=SubjectType(assertion.subject_type),
        subject_id=assertion.subject_id,
        field=assertion.field,
        value=assertion.value,
        status=AssertionStatus(assertion.status),
        asserted_by=assertion.asserted_by,
        citation_ids=list(assertion.citation_ids or []),
        supersedes_id=assertion.supersedes_id,
        sensitivity=Sensitivity(assertion.sensitivity) if assertion.sensitivity else None,
        created_at=assertion.created_at,
    )


def visible_assertions(ctx: SpaceContext, rows: Sequence[Assertion]) -> list[Assertion]:
    cache: dict[tuple[str, uuid.UUID], bool] = {}
    visible: list[Assertion] = []
    for row in rows:
        if row.sensitivity is not None and row.asserted_by != ctx.sub:
            key = (row.subject_type, row.subject_id)
            if key not in cache:
                cache[key] = subject_about_living(ctx, row.subject_type, row.subject_id)
            if not sensitive_visible(row.sensitivity, row.asserted_by, ctx.sub, cache[key]):
                continue
        visible.append(row)
    return visible


def get_current(ctx: SpaceContext, assertion_id: uuid.UUID) -> Assertion:
    """The assertion, which must be visible and still the head of its chain."""
    row = ctx.db.scalar(
        select(Assertion).where(
            Assertion.id == assertion_id, Assertion.family_space_id == ctx.space_id
        )
    )
    if row is None or not visible_assertions(ctx, [row]):
        raise not_found("assertion_not_found", "Assertion not found.")
    newer = ctx.db.scalar(select(Assertion.id).where(Assertion.supersedes_id == row.id))
    if newer is not None:
        raise conflict(
            "assertion_superseded", "The assertion has a newer version; act on that one."
        )
    return row


def append_version(
    ctx: SpaceContext,
    previous: Assertion,
    *,
    status: AssertionStatus,
    citation_ids: Sequence[uuid.UUID],
) -> Assertion:
    """Write the next version of an assertion. The previous row is never modified."""
    if status is AssertionStatus.ACCEPTED and not citation_ids:
        raise unprocessable(
            "citation_required", "Accepting an assertion needs at least one citation."
        )
    row = Assertion(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        subject_type=previous.subject_type,
        subject_id=previous.subject_id,
        field=previous.field,
        value=previous.value,
        status=status.value,
        asserted_by=ctx.sub,
        citation_ids=list(citation_ids),
        supersedes_id=previous.id,
        sensitivity=previous.sensitivity,
    )
    ctx.db.add(row)
    audit.record(
        ctx,
        "assertion",
        row.id,
        RevisionAction.CREATE,
        {
            "supersedes_id": previous.id,
            "status": {"from": previous.status, "to": status.value},
            "citation_ids": list(citation_ids),
        },
    )
    return row


def citations_out(ctx: SpaceContext, ids: Iterable[uuid.UUID]) -> list[CitationOut]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []
    rows = ctx.db.scalars(
        select(Citation).where(Citation.id.in_(wanted)).order_by(Citation.created_at, Citation.id)
    ).all()
    return [CitationOut.model_validate(row) for row in rows]


def citations_for_subjects(
    ctx: SpaceContext, subjects: Sequence[tuple[SubjectType, uuid.UUID]]
) -> list[CitationOut]:
    """Citations behind the current, visible assertions about these subjects."""
    if not subjects:
        return []
    ids = [subject_id for _, subject_id in subjects]
    rows = ctx.db.scalars(
        current_assertions().where(
            Assertion.family_space_id == ctx.space_id,
            Assertion.subject_id.in_(ids),
            Assertion.status != AssertionStatus.RETRACTED.value,
        )
    ).all()
    allowed = {(t.value, i) for t, i in subjects}
    rows = [row for row in rows if (row.subject_type, row.subject_id) in allowed]
    citation_ids = [cid for row in visible_assertions(ctx, rows) for cid in row.citation_ids]
    return citations_out(ctx, citation_ids)
