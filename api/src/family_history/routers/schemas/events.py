"""Events, participants, relationships and places."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from family_history.models.enums import (
    EventType,
    ParticipantRole,
    PartnerStatus,
    Pedigree,
    PlaceKind,
    RelationshipType,
    Sensitivity,
)
from family_history.routers.schemas.common import (
    ApiModel,
    InputModel,
    LongText,
    MediumText,
    UtcDateTime,
)

# GEDCOM 7 DateValue text: uppercase tokens such as `ABT 1890`, `BET 1850 AND 1860`,
# `12 MAR 1901` or `JULIAN 1700`. The domain library parses it; the API keeps it verbatim.
DateValue = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9_]+( [A-Z0-9_]+)*$", max_length=100)]
InegiCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{2,12}$")]


class ParticipantIn(InputModel):
    person_id: uuid.UUID
    role: ParticipantRole


class Participant(ApiModel):
    person_id: uuid.UUID
    role: ParticipantRole


class EventCreate(InputModel):
    type: EventType
    date_value: DateValue | None = None
    place_id: uuid.UUID | None = None
    description: LongText | None = None
    sensitivity: Sensitivity | None = Field(
        default=None,
        description="Defaults to `religion` for sacraments and `health` for medical events.",
    )
    participants: list[ParticipantIn] = Field(min_length=1, max_length=50)


class EventPatch(InputModel):
    type: EventType | None = None
    date_value: DateValue | None = None
    place_id: uuid.UUID | None = None
    description: LongText | None = None
    sensitivity: Sensitivity | None = None
    participants: list[ParticipantIn] | None = Field(default=None, min_length=1, max_length=50)


class Event(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    type: EventType
    date_value: str | None
    date_earliest: date | None
    date_latest: date | None
    place_id: uuid.UUID | None
    place: str | None
    description: str | None
    sensitivity: Sensitivity | None
    participants: list[Participant]
    created_by: str
    created_at: UtcDateTime
    updated_at: UtcDateTime


_QUALIFIERS: dict[RelationshipType, frozenset[str]] = {
    RelationshipType.PARENT_CHILD: frozenset(p.value for p in Pedigree),
    RelationshipType.UNION: frozenset(p.value for p in PartnerStatus),
}


class RelationshipCreate(InputModel):
    """`qualifier` is the pedigree for `parent_child` (`birth`, `adopted`, `foster`, `step`;
    `from_person_id` is the parent) and the partner status for `union` (`married`,
    `union_libre`, `partner`, `separated`, `divorced`). Civil and religious marriages are
    events, not qualifiers."""

    type: RelationshipType
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID
    qualifier: str

    @model_validator(mode="after")
    def _qualifier_matches_type(self) -> RelationshipCreate:
        if self.from_person_id == self.to_person_id:
            raise ValueError("a relationship needs two different people")
        if self.qualifier not in _QUALIFIERS[self.type]:
            raise ValueError(f"qualifier is not valid for {self.type.value}")
        return self

    @property
    def pedigree(self) -> Pedigree | None:
        return Pedigree(self.qualifier) if self.type is RelationshipType.PARENT_CHILD else None

    @property
    def partner_status(self) -> PartnerStatus | None:
        return PartnerStatus(self.qualifier) if self.type is RelationshipType.UNION else None


class Relationship(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    type: RelationshipType
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID
    qualifier: str
    created_at: UtcDateTime


class PlaceCreate(InputModel):
    name: MediumText
    kind: PlaceKind
    parent_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    inegi_code: InegiCode | None = None

    @model_validator(mode="after")
    def _valid_range(self) -> PlaceCreate:
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not be after valid_to")
        return self


class Place(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    name: str
    kind: PlaceKind
    parent_id: uuid.UUID | None
    valid_from: date | None
    valid_to: date | None
    inegi_code: str | None
    created_at: UtcDateTime
