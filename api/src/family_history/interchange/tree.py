"""The neutral in-memory family tree every interchange path goes through.

Loaders build a `Tree` (from the database, a native JSON export, a GEDCOM file or the synthetic
generator); writers turn one into bytes or into rows. Entities point at each other by `ref`, a
string that is a database id while loading and an export-local id (P1, E1, ...) once
`native.canonicalize` has run. `order` is a tie-break for entities whose exported content is
identical: the database id, or the position in an imported file (see persist.OrderedIds).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class TName:
    given: str | None = None
    apellido_paterno: str | None = None
    apellido_materno: str | None = None
    extra_surnames: list[str] = field(default_factory=list)
    particles: dict[str, str] = field(default_factory=dict)
    nombre_de_pila: str | None = None
    nombre_usado: str | None = None
    nicknames: list[str] = field(default_factory=list)
    name_type: str = "birth"
    lang: str = "es-MX"
    surname_order: str = "paterno_materno"
    is_primary: bool = False


@dataclass
class TPerson:
    ref: str
    sex: str = "U"
    visibility: str = "space"
    names: list[TName] = field(default_factory=list)
    living_status: str = "unknown"  # derived; loaded for privacy markers, never exported
    order: str = ""


@dataclass
class TPlace:
    ref: str
    name: str
    kind: str = "other"
    parent: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    inegi_code: str | None = None
    order: str = ""


@dataclass
class TSource:
    ref: str
    type: str
    title: str
    repository: str | None = None
    locator: dict[str, str] = field(default_factory=dict)
    order: str = ""


@dataclass
class TCitation:
    ref: str
    source: str
    page: str | None = None
    foja: str | None = None
    partida: str | None = None
    quality: int | None = None
    extracted_text: str | None = None
    order: str = ""


@dataclass
class TParticipant:
    person: str
    role: str


@dataclass
class TAssociation:
    person: str
    role: str
    phrase: str | None = None


@dataclass
class TEvent:
    ref: str
    type: str
    date_value: str | None = None
    date_original: str | None = None
    place: str | None = None
    description: str | None = None
    sensitivity: str | None = None
    participants: list[TParticipant] = field(default_factory=list)
    associations: list[TAssociation] = field(default_factory=list)
    order: str = ""


@dataclass
class TUnion:
    ref: str
    partners: tuple[str, str]
    status: str = "married"
    order: str = ""


@dataclass
class TParentLink:
    ref: str
    parent: str
    child: str
    pedigree: str = "birth"
    order: str = ""


@dataclass
class TAssertion:
    ref: str
    subject_type: str
    subject: str
    field: str
    value: Any
    status: str
    sensitivity: str | None = None
    citations: list[str] = dataclasses.field(default_factory=list)
    order: str = ""


@dataclass
class Tree:
    people: list[TPerson] = field(default_factory=list)
    places: list[TPlace] = field(default_factory=list)
    sources: list[TSource] = field(default_factory=list)
    citations: list[TCitation] = field(default_factory=list)
    events: list[TEvent] = field(default_factory=list)
    unions: list[TUnion] = field(default_factory=list)
    parent_links: list[TParentLink] = field(default_factory=list)
    assertions: list[TAssertion] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "people": len(self.people),
            "places": len(self.places),
            "sources": len(self.sources),
            "citations": len(self.citations),
            "events": len(self.events),
            "unions": len(self.unions),
            "parent_child": len(self.parent_links),
            "assertions": len(self.assertions),
        }


# Assertion fields the interchange formats give a meaning to.
FIELD_OCCURRED = "occurred"  # "this event happened": carries the event's citations
FIELD_IDENTITY = "identity"  # "this person existed": carries citations about the person
FIELD_CAUSE_OF_DEATH = "cause_of_death"
