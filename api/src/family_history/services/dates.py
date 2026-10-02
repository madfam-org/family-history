"""Event dates through `family_history.domain.dates`.

An event date arrives either as `date_value` (GEDCOM 7 DateValue text, canonicalized) or as
`date_original` (what the family typed, read by `parse_user_date_es` and, failing that, by the
strict GEDCOM parser). The API stores the canonical value, the original text and the bounds the
domain computes; `date_display` renders the canonical value in Spanish and English.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from family_history.domain.dates import (
    DateBoundsError,
    DateKind,
    DateParseError,
    DateValue,
    format_date_value,
    humanize_en,
    humanize_es,
    parse_date_value,
    parse_user_date_es,
)
from family_history.errors import unprocessable

AMBIGUOUS = "ambiguous_date"
INVALID = "invalid_date"


@dataclass(frozen=True)
class EventDate:
    """What the `event` row stores about a date."""

    value: str | None
    original: str | None
    earliest: date | None
    latest: date | None

    @classmethod
    def empty(cls) -> EventDate:
        return cls(None, None, None, None)


def bounds(value: DateValue) -> tuple[date | None, date | None]:
    """Inclusive proleptic Gregorian bounds, or open ends when a calendar has none in range."""
    try:
        result = value.bounds()
    except DateBoundsError:  # includes UnsupportedCalendarError (French Republican, Hebrew)
        return None, None
    return result.earliest, result.latest


def from_value(value: DateValue, original: str | None) -> EventDate:
    if value.kind is DateKind.EMPTY:
        return EventDate(None, original, None, None)
    earliest, latest = bounds(value)
    return EventDate(format_date_value(value), original, earliest, latest)


def parse_canonical(text: str) -> DateValue:
    """Strict GEDCOM 7 DateValue; any failure is `422 invalid_date`."""
    try:
        return parse_date_value(text)
    except DateParseError as exc:
        raise unprocessable(INVALID, "The date is not a valid GEDCOM 7 date value.") from exc


def parse_original(text: str) -> DateValue:
    """What a person typed: Spanish first, then GEDCOM syntax. Never guesses.

    An ambiguous Spanish date («1890-1895», «03-04-90») is `422 ambiguous_date` unless the strict
    grammar reads it; anything neither parser reads is `422 invalid_date`.
    """
    try:
        return parse_user_date_es(text)
    except DateParseError as spanish_error:
        try:
            return parse_date_value(text)
        except DateParseError as exc:
            if spanish_error.code == AMBIGUOUS:
                raise unprocessable(
                    AMBIGUOUS, "The date is ambiguous; write it with words or as a range."
                ) from exc
            raise unprocessable(INVALID, "The date could not be read.") from exc


def event_date(date_value: str | None, date_original: str | None) -> EventDate:
    """Parse one of the two inputs (the schema rejects both at once)."""
    if date_original is not None:
        return from_value(parse_original(date_original), date_original)
    if date_value is not None:
        return from_value(parse_canonical(date_value), None)
    return EventDate.empty()


def stored_value(text: str | None) -> DateValue | None:
    """The stored canonical value, parsed again (None when absent or unreadable)."""
    if not text:
        return None
    try:
        return parse_date_value(text)
    except DateParseError:
        return None


@dataclass(frozen=True)
class Display:
    es: str
    en: str


def display(text: str | None) -> Display | None:
    value = stored_value(text)
    if value is None or value.kind is DateKind.EMPTY:
        return None
    return Display(es=humanize_es(value), en=humanize_en(value))
