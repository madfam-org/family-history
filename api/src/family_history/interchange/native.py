"""The lossless native export, `family-history-tree/v1`.

The format is these pydantic models; `packages/contracts/family-history-tree.v1.schema.json` is
generated from them (`python -m family_history.cli openapi`, drift-checked in CI). Output is
deterministic: export-local ids (P1, L1, S1, C1, E1, F1, R1, A1) come from a stable sort of each
entity's exported content, keys are sorted, and nothing about the database, the requester or the
time of export is written. Export, import into an empty space and export again therefore give
the same bytes.

Prefixes: P person, L place, S source, C citation, E event, F union (a couple),
R parent-child link, A assertion.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from family_history.interchange.canonical import canonicalize, event_record, name_record
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
from family_history.models.enums import (
    AssertionStatus,
    AssociationRole,
    EventType,
    NameType,
    ParticipantRole,
    PartnerStatus,
    Pedigree,
    PlaceKind,
    Sensitivity,
    Sex,
    SourceType,
    SubjectType,
    SurnameOrder,
    Visibility,
)

FORMAT = "family-history-tree/v1"
SCHEMA_ID = "https://github.com/madfam-org/family-history/blob/main/packages/contracts/family-history-tree.v1.schema.json"

Text = Annotated[str, StringConstraints(min_length=1, max_length=20000)]
PRef = Annotated[str, StringConstraints(pattern=r"^P[1-9][0-9]*$")]
LRef = Annotated[str, StringConstraints(pattern=r"^L[1-9][0-9]*$")]
SRef = Annotated[str, StringConstraints(pattern=r"^S[1-9][0-9]*$")]
CRef = Annotated[str, StringConstraints(pattern=r"^C[1-9][0-9]*$")]
ERef = Annotated[str, StringConstraints(pattern=r"^E[1-9][0-9]*$")]
FRef = Annotated[str, StringConstraints(pattern=r"^F[1-9][0-9]*$")]
RRef = Annotated[str, StringConstraints(pattern=r"^R[1-9][0-9]*$")]
ARef = Annotated[str, StringConstraints(pattern=r"^A[1-9][0-9]*$")]
AnyRef = Annotated[str, StringConstraints(pattern=r"^[PEFRL][1-9][0-9]*$")]


class _Doc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NameDoc(_Doc):
    given: Text | None
    apellido_paterno: Text | None
    apellido_materno: Text | None
    extra_surnames: list[Text]
    particles: dict[Literal["paterno", "materno"], Text]
    nombre_de_pila: Text | None
    nombre_usado: Text | None
    nicknames: list[Text]
    name_type: NameType
    lang: Text
    surname_order: SurnameOrder
    is_primary: bool


class PersonDoc(_Doc):
    id: PRef
    sex: Sex
    visibility: Visibility
    names: list[NameDoc] = Field(min_length=1)


class PlaceDoc(_Doc):
    id: LRef
    name: Text
    kind: PlaceKind
    parent: LRef | None
    valid_from: date | None
    valid_to: date | None
    inegi_code: Text | None


class SourceDoc(_Doc):
    id: SRef
    type: SourceType
    title: Text
    repository: Text | None
    locator: dict[str, str]


class CitationDoc(_Doc):
    id: CRef
    source: SRef
    page: Text | None
    foja: Text | None
    partida: Text | None
    quality: int | None = Field(ge=0, le=3)
    extracted_text: Text | None


class ParticipantDoc(_Doc):
    person: PRef
    role: ParticipantRole


class AssociationDoc(_Doc):
    person: PRef
    role: AssociationRole
    phrase: Text | None

    @model_validator(mode="after")
    def _other_has_phrase(self) -> AssociationDoc:
        if self.role is AssociationRole.OTHER and not self.phrase:
            raise ValueError("an association with role other needs a phrase")
        return self


class EventDoc(_Doc):
    id: ERef
    type: EventType
    date_value: Text | None = Field(description="Canonical GEDCOM 7 DateValue.")
    date_original: Text | None
    place: LRef | None
    description: Text | None
    sensitivity: Sensitivity | None
    participants: list[ParticipantDoc]
    associations: list[AssociationDoc]


class UnionDoc(_Doc):
    id: FRef
    partners: list[PRef] = Field(min_length=2, max_length=2)
    status: PartnerStatus


class ParentChildDoc(_Doc):
    id: RRef
    parent: PRef
    child: PRef
    pedigree: Pedigree


class SubjectDoc(_Doc):
    type: SubjectType
    ref: AnyRef


class AssertionDoc(_Doc):
    id: ARef
    subject: SubjectDoc
    field: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{0,99}$")]
    value: JsonValue
    status: AssertionStatus
    sensitivity: Sensitivity | None
    citations: list[CRef]


_SUBJECT_PREFIX = {"person": "P", "event": "E", "place": "L", "relationship": "FR"}


class TreeDocument(_Doc):
    """A family tree exported from family-history (AGPL-3.0-only)."""

    format: Literal["family-history-tree/v1"]
    people: list[PersonDoc]
    places: list[PlaceDoc]
    sources: list[SourceDoc]
    citations: list[CitationDoc]
    events: list[EventDoc]
    unions: list[UnionDoc]
    parent_child: list[ParentChildDoc]
    assertions: list[AssertionDoc]

    @model_validator(mode="after")
    def _references_resolve(self) -> TreeDocument:
        ids: set[str] = set()
        for group in (self.people, self.places, self.sources, self.citations, self.events,
                      self.unions, self.parent_child, self.assertions):  # fmt: skip
            for item in group:
                if item.id in ids:
                    raise ValueError(f"duplicate id {item.id}")
                ids.add(item.id)

        def need(ref: str | None, where: str) -> None:
            if ref is not None and ref not in ids:
                raise ValueError(f"{where} refers to unknown {ref}")

        for place in self.places:
            need(place.parent, place.id)
        _check_acyclic({p.id: p.parent for p in self.places})
        for citation in self.citations:
            need(citation.source, citation.id)
        for event in self.events:
            need(event.place, event.id)
            for part in event.participants:
                need(part.person, event.id)
            for assoc in event.associations:
                need(assoc.person, event.id)
        for union in self.unions:
            if union.partners[0] == union.partners[1]:
                raise ValueError(f"{union.id} needs two different partners")
            for partner in union.partners:
                need(partner, union.id)
        for link in self.parent_child:
            if link.parent == link.child:
                raise ValueError(f"{link.id} links a person to themselves")
            need(link.parent, link.id)
            need(link.child, link.id)
        for assertion in self.assertions:
            if assertion.subject.ref[0] not in _SUBJECT_PREFIX[assertion.subject.type.value]:
                raise ValueError(f"{assertion.id} subject type does not match its ref")
            need(assertion.subject.ref, assertion.id)
            for ref in assertion.citations:
                need(ref, assertion.id)
        return self


def _check_acyclic(parents: dict[str, str | None]) -> None:
    for start in parents:
        seen = {start}
        current = parents.get(start)
        while current is not None:
            if current in seen:
                raise ValueError(f"place {start} has a cyclic parent chain")
            seen.add(current)
            current = parents.get(current)


# -- documents -------------------------------------------------------------------------------


def to_document(tree: Tree) -> TreeDocument:
    """Build the document from a canonicalized tree."""
    data = {
        "format": FORMAT,
        "people": [
            {
                "id": p.ref,
                "sex": p.sex,
                "visibility": p.visibility,
                "names": [name_record(n) for n in p.names],
            }
            for p in tree.people
        ],
        "places": [
            {
                "id": p.ref,
                "name": p.name,
                "kind": p.kind,
                "parent": p.parent,
                "valid_from": p.valid_from,
                "valid_to": p.valid_to,
                "inegi_code": p.inegi_code,
            }
            for p in tree.places
        ],
        "sources": [
            {
                "id": s.ref,
                "type": s.type,
                "title": s.title,
                "repository": s.repository,
                "locator": s.locator,
            }
            for s in tree.sources
        ],
        "citations": [
            {
                "id": c.ref,
                "source": c.source,
                "page": c.page,
                "foja": c.foja,
                "partida": c.partida,
                "quality": c.quality,
                "extracted_text": c.extracted_text,
            }
            for c in tree.citations
        ],
        "events": [{"id": e.ref, **event_record(e)} for e in tree.events],
        "unions": [
            {"id": u.ref, "partners": list(u.partners), "status": u.status} for u in tree.unions
        ],
        "parent_child": [
            {"id": x.ref, "parent": x.parent, "child": x.child, "pedigree": x.pedigree}
            for x in tree.parent_links
        ],
        "assertions": [
            {
                "id": a.ref,
                "subject": {"type": a.subject_type, "ref": a.subject},
                "field": a.field,
                "value": a.value,
                "status": a.status,
                "sensitivity": a.sensitivity,
                "citations": a.citations,
            }
            for a in tree.assertions
        ],
    }
    return TreeDocument.model_validate(data)


def render(document: TreeDocument) -> bytes:
    payload = document.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def export_bytes(tree: Tree) -> bytes:
    """Canonicalize, validate and render: the bytes of a native export."""
    return render(to_document(canonicalize(tree)))


def parse(data: bytes) -> TreeDocument:
    """Validate a native export (pydantic `ValidationError` on any problem)."""
    return TreeDocument.model_validate_json(data)


def to_tree(document: TreeDocument) -> Tree:
    """The tree of a validated document; `order` keeps the file's position for ties."""

    def order(index: int) -> str:
        return f"{index:09d}"

    tree = Tree()
    tree.people = [
        TPerson(
            p.id,
            p.sex.value,
            p.visibility.value,
            [
                TName(
                    given=n.given,
                    apellido_paterno=n.apellido_paterno,
                    apellido_materno=n.apellido_materno,
                    extra_surnames=list(n.extra_surnames),
                    particles={str(k): v for k, v in n.particles.items()},
                    nombre_de_pila=n.nombre_de_pila,
                    nombre_usado=n.nombre_usado,
                    nicknames=list(n.nicknames),
                    name_type=n.name_type.value,
                    lang=n.lang,
                    surname_order=n.surname_order.value,
                    is_primary=n.is_primary,
                )
                for n in p.names
            ],
            order=order(i),
        )
        for i, p in enumerate(document.people)
    ]
    tree.places = [
        TPlace(
            p.id, p.name, p.kind.value, p.parent, p.valid_from, p.valid_to, p.inegi_code, order(i)
        )  # fmt: skip
        for i, p in enumerate(document.places)
    ]
    tree.sources = [
        TSource(s.id, s.type.value, s.title, s.repository, dict(s.locator), order(i))
        for i, s in enumerate(document.sources)
    ]
    tree.citations = [
        TCitation(
            c.id, c.source, c.page, c.foja, c.partida, c.quality, c.extracted_text, order(i)
        )  # fmt: skip
        for i, c in enumerate(document.citations)
    ]
    tree.events = [
        TEvent(
            e.id,
            e.type.value,
            e.date_value,
            e.date_original,
            e.place,
            e.description,
            e.sensitivity.value if e.sensitivity else None,
            [TParticipant(p.person, p.role.value) for p in e.participants],
            [TAssociation(a.person, a.role.value, a.phrase) for a in e.associations],
            order(i),
        )
        for i, e in enumerate(document.events)
    ]
    tree.unions = [
        TUnion(u.id, (u.partners[0], u.partners[1]), u.status.value, order(i))
        for i, u in enumerate(document.unions)
    ]
    tree.parent_links = [
        TParentLink(x.id, x.parent, x.child, x.pedigree.value, order(i))
        for i, x in enumerate(document.parent_child)
    ]
    tree.assertions = [
        TAssertion(
            a.id,
            a.subject.type.value,
            a.subject.ref,
            a.field,
            a.value,
            a.status.value,
            a.sensitivity.value if a.sensitivity else None,
            list(a.citations),
            order(i),
        )
        for i, a in enumerate(document.assertions)
    ]
    return tree


def json_schema() -> dict[str, Any]:
    schema = TreeDocument.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = FORMAT
    return schema


def render_schema() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
