"""Write a `Tree` into a family space, as the member who asked for the import.

Rows are inserted under that member's row-level-security scope, so the database enforces the
same boundary as an API write. Ids come from `OrderedIds`, which keeps the tree's order: two
entities whose exported content is identical re-export in the order they were imported, which
is what makes export → import → export byte-identical. Living status is derived at the end, from
the imported events and their citations; one `revision` row records the whole import.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from family_history.interchange.tree import TName, Tree
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
from family_history.models.enums import RevisionAction
from family_history.services import audit
from family_history.services import names as name_rules
from family_history.services.access import SpaceContext
from family_history.services.dates import EventDate, from_value, stored_value
from family_history.services.living import recompute_living

_LOW_BITS = 40


class OrderedIds:
    """UUIDs that sort in the order they are handed out: a random 88-bit prefix (version 4 and
    variant bits intact) and a 40-bit counter in the node field."""

    def __init__(self) -> None:
        self._base = uuid.uuid4().int & ~((1 << _LOW_BITS) - 1)
        self._next = 0

    def __call__(self) -> uuid.UUID:
        self._next += 1
        if self._next >= 1 << _LOW_BITS:
            raise OverflowError("too many ids for one import")
        return uuid.UUID(int=self._base + self._next)


class PersistError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Persisted:
    counts: dict[str, int]
    people: list[uuid.UUID]


def _name_form(space_id: uuid.UUID, person_id: uuid.UUID, position: int, name: TName) -> NameForm:
    return NameForm(
        id=uuid.uuid4(),
        family_space_id=space_id,
        person_id=person_id,
        position=position,
        given=name.given,
        apellido_paterno=name.apellido_paterno,
        apellido_materno=name.apellido_materno,
        extra_surnames=list(name.extra_surnames),
        particles={k: v for k, v in name.particles.items() if v},
        nombre_de_pila=name.nombre_de_pila,
        nombre_usado=name.nombre_usado,
        nicknames=list(name.nicknames),
        name_type=name.name_type,
        lang=name.lang,
        surname_order=name.surname_order,
        is_primary=False,
    )


def _event_date(date_value: str | None, date_original: str | None) -> EventDate:
    parsed = stored_value(date_value)
    if date_value and parsed is None:
        raise PersistError("invalid_date", "An event date is not a valid GEDCOM 7 date value.")
    if parsed is None:
        return EventDate(None, date_original, None, None)
    return from_value(parsed, date_original)


def persist_tree(ctx: SpaceContext, tree: Tree, *, source: str) -> Persisted:
    """Insert every entity of `tree` into `ctx.space_id`. The caller commits."""
    db, space = ctx.db, ctx.space_id
    next_id = OrderedIds()
    ids: dict[str, uuid.UUID] = {}

    def new(ref: str) -> uuid.UUID:
        ids[ref] = next_id()
        return ids[ref]

    for place in tree.places:
        db.add(
            Place(
                id=new(place.ref),
                family_space_id=space,
                name=place.name,
                kind=place.kind,
                parent_id=ids[place.parent] if place.parent else None,
                valid_from=place.valid_from,
                valid_to=place.valid_to,
                inegi_code=place.inegi_code,
                search_text=name_rules.normalize(place.name),
                created_by=ctx.sub,
            )
        )
        db.flush()  # a child place's composite key needs its parent row
    for src in tree.sources:
        db.add(
            Source(
                id=new(src.ref),
                family_space_id=space,
                type=src.type,
                title=src.title,
                repository=src.repository,
                locator=dict(src.locator),
                created_by=ctx.sub,
            )
        )
    db.flush()
    for citation in tree.citations:
        db.add(
            Citation(
                id=new(citation.ref),
                family_space_id=space,
                source_id=ids[citation.source],
                page=citation.page,
                foja=citation.foja,
                partida=citation.partida,
                quality=citation.quality,
                extracted_text=citation.extracted_text,
                created_by=ctx.sub,
            )
        )
    db.flush()
    people: list[uuid.UUID] = []
    for member in tree.people:
        person = Person(
            id=new(member.ref),
            family_space_id=space,
            sex=member.sex,
            visibility=member.visibility,
            living_status="unknown",
            created_by=ctx.sub,
        )
        forms = [_name_form(space, person.id, i, n) for i, n in enumerate(member.names)]
        flagged = [form for form, n in zip(forms, member.names, strict=True) if n.is_primary]
        (flagged or forms)[0].is_primary = True
        person.names.extend(forms)
        person.search_tokens = name_rules.search_tokens(forms)
        person.sort_name = name_rules.sort_key(name_rules.primary_name(forms))
        db.add(person)
        people.append(person.id)
    db.flush()
    for item in tree.events:
        parsed = _event_date(item.date_value, item.date_original)
        event = Event(
            id=new(item.ref),
            family_space_id=space,
            type=item.type,
            date_value=parsed.value,
            date_original=parsed.original,
            date_earliest=parsed.earliest,
            date_latest=parsed.latest,
            place_id=ids[item.place] if item.place else None,
            description=item.description,
            sensitivity=item.sensitivity,
            created_by=ctx.sub,
        )
        db.add(event)
        db.flush()
        for person_ref, role in dict.fromkeys((p.person, p.role) for p in item.participants):
            db.add(
                EventParticipant(
                    family_space_id=space, event_id=event.id, person_id=ids[person_ref], role=role
                )
            )
        seen: set[tuple[str, str]] = set()
        for assoc in item.associations:
            if (assoc.person, assoc.role) in seen:
                continue
            seen.add((assoc.person, assoc.role))
            db.add(
                Association(
                    id=next_id(),
                    family_space_id=space,
                    event_id=event.id,
                    person_id=ids[assoc.person],
                    role=assoc.role,
                    phrase=assoc.phrase if assoc.phrase or assoc.role != "other" else "Otro papel",
                    created_by=ctx.sub,
                )
            )
    for union in tree.unions:
        db.add(
            Relationship(
                id=new(union.ref),
                family_space_id=space,
                type="union",
                from_person_id=ids[union.partners[0]],
                to_person_id=ids[union.partners[1]],
                partner_status=union.status,
                created_by=ctx.sub,
            )
        )
    for link in tree.parent_links:
        db.add(
            Relationship(
                id=new(link.ref),
                family_space_id=space,
                type="parent_child",
                from_person_id=ids[link.parent],
                to_person_id=ids[link.child],
                pedigree=link.pedigree,
                created_by=ctx.sub,
            )
        )
    db.flush()
    for assertion in tree.assertions:
        db.add(
            Assertion(
                id=new(assertion.ref),
                family_space_id=space,
                subject_type=assertion.subject_type,
                subject_id=ids[assertion.subject],
                field=assertion.field,
                value=assertion.value,
                status=assertion.status,
                asserted_by=ctx.sub,
                citation_ids=[ids[c] for c in assertion.citations],
                sensitivity=assertion.sensitivity,
            )
        )
    db.flush()
    recompute_living(ctx, people)
    counts = tree.counts()
    audit.record(ctx, "import", next_id(), RevisionAction.CREATE, {"source": source, **counts})
    return Persisted(counts=counts, people=people)
