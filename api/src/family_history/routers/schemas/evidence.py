"""Sources, citations and assertions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, JsonValue, StringConstraints, field_validator

from family_history.models.enums import AssertionStatus, Sensitivity, SourceType, SubjectType
from family_history.routers.schemas.common import ApiModel, InputModel, LongText, MediumText

LocatorKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
LocatorValue = Annotated[str, StringConstraints(min_length=1, max_length=300)]
CitationRef = Annotated[str, StringConstraints(min_length=1, max_length=100)]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]{0,99}$")]

MAX_VALUE_BYTES = 10_000


class SourceCreate(InputModel):
    type: SourceType
    title: MediumText
    repository: MediumText | None = None
    locator: dict[LocatorKey, LocatorValue] = Field(default_factory=dict, max_length=20)


class Source(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    type: SourceType
    title: str
    repository: str | None
    locator: dict[str, str]
    created_at: datetime


class CitationCreate(InputModel):
    page: CitationRef | None = None
    foja: CitationRef | None = None
    partida: CitationRef | None = None
    quality: int | None = Field(default=None, ge=0, le=3)
    extracted_text: LongText | None = None


class Citation(ApiModel):
    id: uuid.UUID
    source_id: uuid.UUID
    page: str | None
    foja: str | None
    partida: str | None
    quality: int | None
    extracted_text: str | None
    created_at: datetime


def _bounded(value: Any) -> Any:
    if len(json.dumps(value, ensure_ascii=False)) > MAX_VALUE_BYTES:
        raise ValueError("value is too large")
    return value


class AssertionCreate(InputModel):
    subject_type: SubjectType
    subject_id: uuid.UUID
    field: FieldName
    value: JsonValue
    status: AssertionStatus = AssertionStatus.SUGGESTED
    citation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    sensitivity: Sensitivity | None = None

    @field_validator("value")
    @classmethod
    def _value_size(cls, value: JsonValue) -> JsonValue:
        bounded: JsonValue = _bounded(value)
        return bounded


class AssertionStatusChange(InputModel):
    status: AssertionStatus
    citation_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class AssertionCitationLink(InputModel):
    citation_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class Assertion(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    subject_type: SubjectType
    subject_id: uuid.UUID
    field: str
    value: JsonValue
    status: AssertionStatus
    asserted_by: str
    citation_ids: list[uuid.UUID]
    supersedes_id: uuid.UUID | None
    sensitivity: Sensitivity | None
    created_at: datetime
