"""Events, participants, relationships and places."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from family_history.models.enums import (
    ParentChildQualifier,
    ParticipantRole,
    PlaceKind,
    RelationshipType,
    Sensitivity,
    UnionQualifier,
    UnionStatus,
)
from family_history.routers.schemas.common import ApiModel, InputModel, LongText, MediumText

EventType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,49}$")]
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
    type: str
    date_value: str | None
    date_earliest: date | None
    date_latest: date | None
    place_id: uuid.UUID | None
    place: str | None
    description: str | None
    sensitivity: Sensitivity | None
    participants: list[Participant]
    created_by: str
    created_at: datetime
    updated_at: datetime


class RelationshipCreate(InputModel):
    """For `parent_child`, `from_person_id` is the parent and `to_person_id` the child."""

    type: RelationshipType
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID
    qualifier: str
    status: UnionStatus | None = None

    @model_validator(mode="after")
    def _qualifier_matches_type(self) -> RelationshipCreate:
        if self.from_person_id == self.to_person_id:
            raise ValueError("a relationship needs two different people")
        if self.type is RelationshipType.PARENT_CHILD:
            if self.qualifier not in {q.value for q in ParentChildQualifier}:
                raise ValueError("qualifier is not valid for parent_child")
            if self.status is not None:
                raise ValueError("status applies to unions only")
        else:
            if self.qualifier not in {q.value for q in UnionQualifier}:
                raise ValueError("qualifier is not valid for union")
            if self.status is None:
                self.status = UnionStatus.ACTIVE
        return self


class Relationship(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    type: RelationshipType
    from_person_id: uuid.UUID
    to_person_id: uuid.UUID
    qualifier: str
    status: UnionStatus | None
    created_at: datetime


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
    created_at: datetime
