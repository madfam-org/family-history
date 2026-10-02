"""Load what one member may see of a family space as a `Tree` (the export privacy rule).

An export holds exactly what the requester can read through the API:

- people who are not soft-deleted, and private people only when the requester created them;
- events, minus those carrying a sensitivity class about someone treated as living that the
  requester did not record (and participants or associations pointing at hidden people);
- relationships whose both ends are exported;
- current assertions under the same sensitivity rule, about exported subjects only;
- every place, source and citation of the space (they describe records, not people).
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select

from family_history.interchange.tree import (
    TAssertion,
    TAssociation,
    TCitation,
    TEvent,
    TName,
    TParentLink,
    TParticipant,
    TPerson,
    TPlace,
    Tree,
    TSource,
    TUnion,
)
from family_history.models import (
    Assertion,
    Association,
    Citation,
    Event,
    EventParticipant,
    NameForm,
    Person,
    Place,
    Relationship,
    Source,
)
from family_history.models.enums import ParticipantRole, RelationshipType, SubjectType
from family_history.services.access import SpaceContext
from family_history.services.evidence import current_assertions
from family_history.services.privacy import sensitive_visible, treated_as_living, visible_people


def _name(row: NameForm) -> TName:
    particles = {k: str(v) for k, v in (row.particles or {}).items() if isinstance(v, str) and v}
    return TName(
        given=row.given,
        apellido_paterno=row.apellido_paterno,
        apellido_materno=row.apellido_materno,
        extra_surnames=list(row.extra_surnames or []),
        particles=particles,
        nombre_de_pila=row.nombre_de_pila,
        nombre_usado=row.nombre_usado,
        nicknames=list(row.nicknames or []),
        name_type=row.name_type,
        lang=row.lang,
        surname_order=row.surname_order,
        is_primary=row.is_primary,
    )


def _people(ctx: SpaceContext) -> list[TPerson]:
    rows = ctx.db.scalars(
        select(Person).where(Person.family_space_id == ctx.space_id, visible_people(ctx.sub))
    ).all()
    return [
        TPerson(
            ref=str(row.id),
            sex=row.sex,
            visibility=row.visibility,
            names=[_name(n) for n in sorted(row.names, key=lambda n: (n.position, str(n.id)))],
            living_status=row.living_status,
            order=str(row.id),
        )
        for row in rows
    ]


def _events(
    ctx: SpaceContext, people: dict[str, TPerson], about_living: dict[str, bool]
) -> list[TEvent]:
    """Visible events; `about_living` receives, for every event, whether a principal (seen or
    not) is treated as living."""
    events = ctx.db.scalars(select(Event).where(Event.family_space_id == ctx.space_id)).all()
    participants: dict[uuid.UUID, list[EventParticipant]] = defaultdict(list)
    for row in ctx.db.scalars(
        select(EventParticipant).where(EventParticipant.family_space_id == ctx.space_id)
    ).all():
        participants[row.event_id].append(row)
    associations: dict[uuid.UUID, list[Association]] = defaultdict(list)
    for assoc in ctx.db.scalars(
        select(Association).where(Association.family_space_id == ctx.space_id)
    ).all():
        associations[assoc.event_id].append(assoc)
    out: list[TEvent] = []
    for event in events:
        rows = participants.get(event.id, [])
        principals = [r for r in rows if r.role == ParticipantRole.PRINCIPAL.value]
        living = any(
            treated_as_living(people[str(r.person_id)].living_status)
            if str(r.person_id) in people
            else True
            for r in principals
        )
        about_living[str(event.id)] = living
        if not sensitive_visible(event.sensitivity, event.created_by, ctx.sub, living):
            continue
        shown = [r for r in rows if str(r.person_id) in people]
        if rows and not shown:
            continue  # an event only about people the requester cannot see
        out.append(
            TEvent(
                ref=str(event.id),
                type=event.type,
                date_value=event.date_value,
                date_original=event.date_original,
                place=str(event.place_id) if event.place_id else None,
                description=event.description,
                sensitivity=event.sensitivity,
                participants=[TParticipant(str(r.person_id), r.role) for r in shown],
                associations=[
                    TAssociation(str(a.person_id), a.role, a.phrase)
                    for a in associations.get(event.id, [])
                    if str(a.person_id) in people
                ],
                order=str(event.id),
            )
        )
    return out


def _relationships(ctx: SpaceContext, tree: Tree, people: dict[str, TPerson]) -> None:
    rows = ctx.db.scalars(
        select(Relationship).where(Relationship.family_space_id == ctx.space_id)
    ).all()
    for row in rows:
        a, b = str(row.from_person_id), str(row.to_person_id)
        if a not in people or b not in people:
            continue
        if row.type == RelationshipType.PARENT_CHILD.value:
            tree.parent_links.append(
                TParentLink(str(row.id), a, b, row.pedigree or "birth", order=str(row.id))
            )
        else:
            tree.unions.append(
                TUnion(str(row.id), (a, b), row.partner_status or "married", order=str(row.id))
            )


def _assertions(
    ctx: SpaceContext,
    tree: Tree,
    exported: dict[str, set[str]],
    about_living: dict[str, bool],
) -> None:
    """Current assertions about exported subjects, under the API's sensitivity rule: a
    sensitive assertion about someone treated as living only for whoever made it."""
    rows = ctx.db.scalars(
        current_assertions().where(Assertion.family_space_id == ctx.space_id)
    ).all()
    citations = {c.ref for c in tree.citations}
    for row in rows:
        subject = str(row.subject_id)
        if subject not in exported.get(row.subject_type, set()):
            continue
        if row.sensitivity is not None and row.asserted_by != ctx.sub:
            living = about_living.get(f"{row.subject_type}:{subject}", True)
            if not sensitive_visible(row.sensitivity, row.asserted_by, ctx.sub, living):
                continue
        tree.assertions.append(
            TAssertion(
                ref=str(row.id),
                subject_type=row.subject_type,
                subject=subject,
                field=row.field,
                value=row.value,
                status=row.status,
                sensitivity=row.sensitivity,
                citations=[str(c) for c in row.citation_ids if str(c) in citations],
                order=str(row.id),
            )
        )


def load_tree(ctx: SpaceContext) -> Tree:
    tree = Tree()
    tree.people = _people(ctx)
    people = {p.ref: p for p in tree.people}
    tree.places = [
        TPlace(
            ref=str(p.id),
            name=p.name,
            kind=p.kind,
            parent=str(p.parent_id) if p.parent_id else None,
            valid_from=p.valid_from,
            valid_to=p.valid_to,
            inegi_code=p.inegi_code,
            order=str(p.id),
        )
        for p in ctx.db.scalars(select(Place).where(Place.family_space_id == ctx.space_id)).all()
    ]
    tree.sources = [
        TSource(
            ref=str(s.id),
            type=s.type,
            title=s.title,
            repository=s.repository,
            locator={k: str(v) for k, v in (s.locator or {}).items()},
            order=str(s.id),
        )
        for s in ctx.db.scalars(select(Source).where(Source.family_space_id == ctx.space_id))
    ]
    tree.citations = [
        TCitation(
            ref=str(c.id),
            source=str(c.source_id),
            page=c.page,
            foja=c.foja,
            partida=c.partida,
            quality=c.quality,
            extracted_text=c.extracted_text,
            order=str(c.id),
        )
        for c in ctx.db.scalars(select(Citation).where(Citation.family_space_id == ctx.space_id))
    ]
    event_living: dict[str, bool] = {}
    tree.events = _events(ctx, people, event_living)
    _relationships(ctx, tree, people)
    exported = {
        SubjectType.PERSON.value: set(people),
        SubjectType.EVENT.value: {e.ref for e in tree.events},
        SubjectType.RELATIONSHIP.value: {u.ref for u in tree.unions}
        | {link.ref for link in tree.parent_links},
        SubjectType.PLACE.value: {p.ref for p in tree.places},
    }
    about_living = {
        f"{SubjectType.EVENT.value}:{ref}": living for ref, living in event_living.items()
    }
    for ref, person in people.items():
        about_living[f"{SubjectType.PERSON.value}:{ref}"] = treated_as_living(person.living_status)
    for union in tree.unions:
        about_living[f"{SubjectType.RELATIONSHIP.value}:{union.ref}"] = any(
            treated_as_living(people[p].living_status) for p in union.partners
        )
    for link in tree.parent_links:
        about_living[f"{SubjectType.RELATIONSHIP.value}:{link.ref}"] = any(
            treated_as_living(people[p].living_status) for p in (link.parent, link.child)
        )
    for place in tree.places:
        about_living[f"{SubjectType.PLACE.value}:{place.ref}"] = False
    _assertions(ctx, tree, exported, about_living)
    return tree
