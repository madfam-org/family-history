"""People: names, listing with search and keyset pagination, and the full person view."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from family_history.auth import Principal
from family_history.errors import not_found, unprocessable
from family_history.models import Event, EventParticipant, NameForm, Person, Place, Relationship
from family_history.models.enums import (
    LivingStatus,
    NameType,
    ParticipantRole,
    RelationshipType,
    Sex,
    SubjectType,
    SurnameOrder,
    Visibility,
)
from family_history.routers.schemas.common import EventBrief
from family_history.routers.schemas.events import Relationship as RelationshipOut
from family_history.routers.schemas.people import NameFormIn, NameFormOut, PersonPage, PersonSummary
from family_history.routers.schemas.people import Person as PersonOut
from family_history.services import names as name_rules
from family_history.services import search
from family_history.services.access import SpaceContext, enter_space, user_scoped
from family_history.services.events import date_display, events_out, visible_person_ids
from family_history.services.evidence import citations_for_subjects
from family_history.services.living import is_private
from family_history.services.pagination import (
    decode_cursor,
    decode_ranked_cursor,
    encode_cursor,
    encode_ranked_cursor,
)
from family_history.services.privacy import (
    sensitive_visible,
    treated_as_living,
    visible_people,
)


def set_names(person: Person, names_in: Sequence[NameFormIn]) -> None:
    """Replace every name form. Exactly one is primary: the flagged one, or the first."""
    flagged = [index for index, name in enumerate(names_in) if name.is_primary]
    if len(flagged) > 1:
        raise unprocessable("multiple_primary_names", "Only one name form can be primary.")
    primary_index = flagged[0] if flagged else 0
    person.names.clear()
    for index, name in enumerate(names_in):
        data = name.model_dump()
        particles = {k: v for k, v in (data.pop("particles") or {}).items() if v}
        data["particles"] = particles
        data["is_primary"] = index == primary_index
        data["name_type"] = name.name_type.value
        data["surname_order"] = name.surname_order.value
        person.names.append(
            NameForm(family_space_id=person.family_space_id, position=index, **data)
        )
    primary = name_rules.primary_name(person.names)
    person.search_tokens = name_rules.search_tokens(person.names)
    person.sort_name = name_rules.sort_key(primary)


def names_snapshot(person: Person) -> list[dict[str, Any]]:
    return [
        {
            "given": n.given,
            "apellido_paterno": n.apellido_paterno,
            "apellido_materno": n.apellido_materno,
            "nombre_usado": n.nombre_usado,
            "is_primary": n.is_primary,
        }
        for n in person.names
    ]


def resolve_person(db: Session, principal: Principal, person_id: uuid.UUID) -> SpaceContext:
    """Find which of the caller's spaces holds the person, then enter that space.

    With only `app.user_sub` set, RLS shows rows from every space the caller belongs to.
    """
    user_scoped(db, principal)
    space_id = db.scalar(
        select(Person.family_space_id).where(Person.id == person_id, visible_people(principal.sub))
    )
    if space_id is None:
        raise not_found("person_not_found", "Person not found.")
    return enter_space(db, principal, space_id)


def get_person(ctx: SpaceContext, person_id: uuid.UUID) -> Person:
    person = ctx.db.scalar(
        select(Person).where(
            Person.family_space_id == ctx.space_id,
            Person.id == person_id,
            visible_people(ctx.sub),
        )
    )
    if person is None:
        raise not_found("person_not_found", "Person not found.")
    return person


def _briefs(ctx: SpaceContext, people: Sequence[Person]) -> dict[uuid.UUID, dict[str, EventBrief]]:
    """Birth and death briefs for each person (their principal events)."""
    if not people:
        return {}
    living = {p.id: treated_as_living(p.living_status) for p in people}
    rows = ctx.db.execute(
        select(
            EventParticipant.person_id,
            Event.type,
            Event.date_value,
            Event.sensitivity,
            Event.created_by,
            Place.name,
        )
        .join(Event, Event.id == EventParticipant.event_id)
        .outerjoin(Place, Place.id == Event.place_id)
        .where(
            EventParticipant.person_id.in_(list(living)),
            EventParticipant.role == ParticipantRole.PRINCIPAL.value,
            Event.type.in_(["birth", "death"]),
        )
        .order_by(Event.created_at, Event.id)
    ).all()
    briefs: dict[uuid.UUID, dict[str, EventBrief]] = {}
    for person_id, event_type, date_value, sensitivity, created_by, place in rows:
        if not sensitive_visible(sensitivity, created_by, ctx.sub, living[person_id]):
            continue
        briefs.setdefault(person_id, {}).setdefault(
            event_type,
            EventBrief(date_value=date_value, date_display=date_display(date_value), place=place),
        )
    return briefs


def summaries(ctx: SpaceContext, people: Sequence[Person]) -> list[PersonSummary]:
    briefs = _briefs(ctx, people)
    return [
        PersonSummary(
            id=p.id,
            display_name=name_rules.display_name(name_rules.primary_name(p.names)),
            sort_name=name_rules.sorting_display(name_rules.primary_name(p.names)),
            sex=Sex(p.sex),
            living_status=LivingStatus(p.living_status),
            is_private=is_private(p.living_status, p.visibility),
            birth=briefs.get(p.id, {}).get("birth"),
            death=briefs.get(p.id, {}).get("death"),
            visibility=Visibility(p.visibility),
        )
        for p in people
    ]


def list_people(ctx: SpaceContext, q: str | None, limit: int, cursor: str | None) -> PersonPage:
    """Without `q`: surname order. With `q`: exact, then variant, then prefix matches
    (services/search.py), each group in surname order."""
    query = select(Person).where(Person.family_space_id == ctx.space_id, visible_people(ctx.sub))
    compiled = search.compile_search(search.plan(q))
    if compiled is None:
        if cursor:
            sort_key, last_id = decode_cursor(cursor)
            query = query.where(
                tuple_(Person.sort_name, Person.id) > tuple_(literal(sort_key), literal(last_id))
            )
        rows = ctx.db.scalars(query.order_by(Person.sort_name, Person.id).limit(limit + 1)).all()
        page = list(rows[:limit])
        has_more = len(rows) > limit and bool(page)
        next_cursor = encode_cursor(page[-1].sort_name, page[-1].id) if has_more else None
        return PersonPage(items=summaries(ctx, page), next_cursor=next_cursor)

    rank: ColumnElement[int] = compiled.rank
    query = query.where(compiled.where)
    if cursor:
        last_rank, sort_key, last_id = decode_ranked_cursor(cursor)
        query = query.where(
            tuple_(rank, Person.sort_name, Person.id)
            > tuple_(literal(last_rank), literal(sort_key), literal(last_id))
        )
    ranked = ctx.db.execute(
        query.add_columns(rank.label("rank"))
        .order_by(rank, Person.sort_name, Person.id)
        .limit(limit + 1)
    ).all()
    page_rows = list(ranked[:limit])
    next_cursor = None
    if len(ranked) > limit and page_rows:
        last_person, last_rank_value = page_rows[-1]
        next_cursor = encode_ranked_cursor(
            int(last_rank_value), last_person.sort_name, last_person.id
        )
    return PersonPage(items=summaries(ctx, [row[0] for row in page_rows]), next_cursor=next_cursor)


def relationships_out(ctx: SpaceContext, rows: Sequence[Relationship]) -> list[RelationshipOut]:
    """Relationships whose both ends the caller can see."""
    people = {r.from_person_id for r in rows} | {r.to_person_id for r in rows}
    visible = visible_person_ids(ctx, people)
    return [
        RelationshipOut(
            id=r.id,
            space_id=r.family_space_id,
            type=RelationshipType(r.type),
            from_person_id=r.from_person_id,
            to_person_id=r.to_person_id,
            qualifier=r.qualifier,
            created_at=r.created_at,
        )
        for r in rows
        if r.from_person_id in visible and r.to_person_id in visible
    ]


def detail(ctx: SpaceContext, person: Person) -> PersonOut:
    event_rows = ctx.db.scalars(
        select(Event)
        .join(EventParticipant, EventParticipant.event_id == Event.id)
        .where(Event.family_space_id == ctx.space_id, EventParticipant.person_id == person.id)
        .distinct()
        .order_by(Event.date_earliest.nulls_last(), Event.created_at, Event.id)
    ).all()
    events = events_out(ctx, event_rows)
    rel_rows = ctx.db.scalars(
        select(Relationship)
        .where(
            Relationship.family_space_id == ctx.space_id,
            or_(Relationship.from_person_id == person.id, Relationship.to_person_id == person.id),
        )
        .order_by(Relationship.created_at, Relationship.id)
    ).all()
    subjects = [(SubjectType.PERSON, person.id)] + [(SubjectType.EVENT, e.id) for e in events]
    return PersonOut(
        id=person.id,
        space_id=person.family_space_id,
        display_name=name_rules.display_name(name_rules.primary_name(person.names)),
        sort_name=name_rules.sorting_display(name_rules.primary_name(person.names)),
        sex=Sex(person.sex),
        living_status=LivingStatus(person.living_status),
        is_private=is_private(person.living_status, person.visibility),
        visibility=Visibility(person.visibility),
        names=[
            NameFormOut(
                id=n.id,
                position=n.position,
                given=n.given,
                apellido_paterno=n.apellido_paterno,
                apellido_materno=n.apellido_materno,
                extra_surnames=list(n.extra_surnames or []),
                particles={k: str(v) for k, v in (n.particles or {}).items()},
                nombre_de_pila=n.nombre_de_pila,
                nombre_usado=n.nombre_usado,
                nicknames=list(n.nicknames or []),
                name_type=NameType(n.name_type),
                lang=n.lang,
                surname_order=SurnameOrder(n.surname_order),
                is_primary=n.is_primary,
            )
            for n in person.names
        ],
        events=events,
        relationships=relationships_out(ctx, rel_rows),
        citations=citations_for_subjects(ctx, subjects),
        created_by=person.created_by,
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


def display_names(ctx: SpaceContext, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display names of the people the caller can see among `ids`."""
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return {}
    rows = ctx.db.scalars(
        select(Person).where(
            Person.family_space_id == ctx.space_id, Person.id.in_(wanted), visible_people(ctx.sub)
        )
    ).all()
    return {p.id: name_rules.display_name(name_rules.primary_name(p.names)) for p in rows}
