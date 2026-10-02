"""Base models and shared shapes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


# Timestamps always leave the API in UTC, whatever the database session's time zone.
UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]


class ApiModel(BaseModel):
    """Response shape. Built from ORM objects or dicts."""

    model_config = ConfigDict(from_attributes=True)


class InputModel(BaseModel):
    """Request body: unknown fields are rejected and strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
MediumText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(max_length=20000)]
LangTag = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")]


class DateDisplay(ApiModel):
    """A date in words: «hacia 1891» / "about 1891" (`domain.dates.humanize_es`/`_en`)."""

    es: str
    en: str


class EventBrief(ApiModel):
    date_value: str | None
    date_display: DateDisplay | None
    place: str | None
