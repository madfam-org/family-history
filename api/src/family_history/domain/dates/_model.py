"""The GEDCOM 7 `DateValue` model, its canonical text form and its day bounds."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ._calendars import (
    Calendar,
    date_from_jdn,
    days_in_month,
    gregorian_to_jdn,
    julian_to_jdn,
    months_for,
)

__all__ = [
    "DEFAULT_APPROX_YEARS",
    "CalendarDate",
    "DateBounds",
    "DateBoundsError",
    "DateKind",
    "DateParseError",
    "DateValue",
    "UnsupportedCalendarError",
    "format_date_value",
]

#: How far `ABT`, `CAL` and `EST` widen a date on each side when computing bounds.
DEFAULT_APPROX_YEARS = 5


class DateParseError(ValueError):
    """Raised when text is not a valid date. The message says what is wrong and where."""

    def __init__(self, message: str, text: str, code: str = "invalid_date") -> None:
        super().__init__(f"{message} (in {text!r})")
        self.reason = message
        self.text = text
        #: Stable snake_case code for UI copy: `invalid_date` or `ambiguous_date`.
        self.code = code


class DateBoundsError(ValueError):
    """Raised when a date's day bounds cannot be expressed as requested."""


class UnsupportedCalendarError(DateBoundsError):
    """Raised for bounds of French Republican or Hebrew dates, which parse but do not convert."""


class DateKind(StrEnum):
    """The shape of a `DateValue`, named after its GEDCOM 7 keyword."""

    EMPTY = "EMPTY"
    DATE = "DATE"
    ABOUT = "ABT"
    CALCULATED = "CAL"
    ESTIMATED = "EST"
    BEFORE = "BEF"
    AFTER = "AFT"
    BETWEEN = "BET"
    FROM = "FROM"
    TO = "TO"
    FROM_TO = "FROM_TO"

    @property
    def is_approximate(self) -> bool:
        """True for `ABT`, `CAL` and `EST` (the GEDCOM `dateApprox` forms)."""
        return self in _APPROX_KINDS

    @property
    def is_range(self) -> bool:
        """True for `BEF`, `AFT` and `BET … AND …` (the GEDCOM `dateRange` forms)."""
        return self in _RANGE_KINDS

    @property
    def is_period(self) -> bool:
        """True for `FROM`, `TO` and `FROM … TO …` (the GEDCOM `DatePeriod` forms)."""
        return self in _PERIOD_KINDS

    @property
    def date_count(self) -> int:
        """How many calendar dates this kind carries: 0, 1 or 2."""
        if self is DateKind.EMPTY:
            return 0
        return 2 if self in (DateKind.BETWEEN, DateKind.FROM_TO) else 1


_APPROX_KINDS = frozenset({DateKind.ABOUT, DateKind.CALCULATED, DateKind.ESTIMATED})
_RANGE_KINDS = frozenset({DateKind.BEFORE, DateKind.AFTER, DateKind.BETWEEN})
_PERIOD_KINDS = frozenset({DateKind.FROM, DateKind.TO, DateKind.FROM_TO})


@dataclass(frozen=True, slots=True)
class CalendarDate:
    """One GEDCOM 7 `date`: `[calendar] [[day] month] year [BCE]`.

    `year` is the year as written (always positive); `bce` marks the `BCE` epoch, which only the
    Gregorian and Julian calendars allow. `month` is the GEDCOM month tag of the calendar.
    """

    year: int
    month: str | None = None
    day: int | None = None
    calendar: Calendar = Calendar.GREGORIAN
    bce: bool = False

    def __post_init__(self) -> None:
        if self.year < 1:
            raise ValueError("year must be 1 or greater; GEDCOM has no year 0 (use BCE)")
        if self.bce and self.calendar not in (Calendar.GREGORIAN, Calendar.JULIAN):
            raise ValueError(f"the {self.calendar.value} calendar has no BCE epoch")
        if self.day is not None and self.month is None:
            raise ValueError("a day needs a month")
        if self.month is not None:
            months = months_for(self.calendar)
            if self.month not in months:
                raise ValueError(
                    f"{self.month!r} is not a {self.calendar.value} month; "
                    f"expected one of {', '.join(months)}"
                )
        if self.day is not None:
            limit = days_in_month(self.calendar, self.astro_year, self.month_number or 1)
            if not 1 <= self.day <= limit:
                raise ValueError(f"day {self.day} is out of range for {self.month} (1 to {limit})")

    @property
    def astro_year(self) -> int:
        """The astronomical year: 1 BCE is 0, 2 BCE is -1."""
        return 1 - self.year if self.bce else self.year

    @property
    def month_number(self) -> int | None:
        """The 1-based month number within the calendar, or None for a year-only date."""
        if self.month is None:
            return None
        return months_for(self.calendar).index(self.month) + 1

    @property
    def precision(self) -> str:
        """`"day"`, `"month"` or `"year"`."""
        if self.day is not None:
            return "day"
        return "month" if self.month is not None else "year"

    def format(self) -> str:
        """Return the canonical GEDCOM 7 text of this date."""
        parts: list[str] = []
        if self.calendar is not Calendar.GREGORIAN:
            parts.append(self.calendar.value)
        if self.day is not None:
            parts.append(str(self.day))
        if self.month is not None:
            parts.append(self.month)
        parts.append(str(self.year))
        if self.bce:
            parts.append("BCE")
        return " ".join(parts)

    def jdn_bounds(self, widen_years: int = 0) -> tuple[int, int]:
        """Return the first and last Julian Day Number this date can denote.

        `widen_years` moves the start that many years earlier and the end that many years later
        (a 29 February end point falls back to 28 February in a common year).
        """
        to_jdn = _jdn_function(self.calendar)
        month = self.month_number
        lo_year, hi_year = self.astro_year - widen_years, self.astro_year + widen_years
        if month is None:
            return to_jdn(lo_year, 1, 1), to_jdn(hi_year, 12, 31)
        lo_last = days_in_month(self.calendar, lo_year, month)
        hi_last = days_in_month(self.calendar, hi_year, month)
        if self.day is not None:
            return (
                to_jdn(lo_year, month, min(self.day, lo_last)),
                to_jdn(hi_year, month, min(self.day, hi_last)),
            )
        return to_jdn(lo_year, month, 1), to_jdn(hi_year, month, hi_last)


def _jdn_function(calendar: Calendar) -> Callable[[int, int, int], int]:
    if calendar is Calendar.GREGORIAN:
        return gregorian_to_jdn
    if calendar is Calendar.JULIAN:
        return julian_to_jdn
    raise UnsupportedCalendarError(
        f"day bounds for the {calendar.value} calendar are not supported; "
        "the date still parses and round-trips"
    )


@dataclass(frozen=True, slots=True)
class DateBounds:
    """Inclusive proleptic Gregorian bounds of a date value. None means open-ended."""

    earliest: dt.date | None
    latest: dt.date | None


@dataclass(frozen=True, slots=True)
class DateValue:
    """A GEDCOM 7 `DateValue` plus its optional `PHRASE` and the text it was read from.

    `first` is the date of single-date kinds and the start of `BET … AND …` and `FROM … TO …`;
    `second` is the end of those two kinds. `original` keeps the source text and does not take
    part in equality.
    """

    kind: DateKind
    first: CalendarDate | None = None
    second: CalendarDate | None = None
    phrase: str | None = None
    original: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        count = self.kind.date_count
        if (self.first is not None) != (count >= 1) or (self.second is not None) != (count == 2):
            raise ValueError(f"a {self.kind.value} date value needs exactly {count} date(s)")
        if self.phrase is not None and not self.phrase.strip():
            raise ValueError("a phrase, when given, must not be blank")
        if self.first is not None and self.second is not None:
            _check_order(self.first, self.second, self.kind)
        if not self.original:
            object.__setattr__(self, "original", format_date_value(self))

    @property
    def is_empty(self) -> bool:
        """True for the empty date value (a `DATE` with no payload, often with a phrase)."""
        return self.kind is DateKind.EMPTY

    def format(self) -> str:
        """Return the canonical GEDCOM 7 text. Same as `format_date_value(self)`."""
        return format_date_value(self)

    def jdn_bounds(self, approx_years: int = DEFAULT_APPROX_YEARS) -> tuple[int | None, int | None]:
        """Return inclusive Julian Day Number bounds; None means open-ended.

        `ABT`, `CAL` and `EST` widen the date by `approx_years` on each side. `BEF x` is no later
        than the end of `x`, and `AFT x` no earlier than its start (GEDCOM 7 semantics). Raises
        `UnsupportedCalendarError` for French Republican and Hebrew dates.
        """
        if approx_years < 0:
            raise ValueError("approx_years must not be negative")
        first, second = self.first, self.second
        if first is None:
            return None, None
        if self.kind.is_approximate:
            return first.jdn_bounds(approx_years)
        lo, hi = first.jdn_bounds()
        if second is not None:
            return lo, second.jdn_bounds()[1]
        if self.kind in (DateKind.BEFORE, DateKind.TO):
            return None, hi
        if self.kind in (DateKind.AFTER, DateKind.FROM):
            return lo, None
        return lo, hi

    def bounds(self, approx_years: int = DEFAULT_APPROX_YEARS) -> DateBounds:
        """Return the bounds as proleptic Gregorian dates (see `jdn_bounds`).

        Raises `DateBoundsError` when a bound falls outside `datetime.date` (before 1 CE or after
        9999); use `jdn_bounds` for those.
        """
        lo, hi = self.jdn_bounds(approx_years)
        return DateBounds(_to_date(lo), _to_date(hi))

    @property
    def earliest(self) -> dt.date | None:
        """The earliest proleptic Gregorian day, with the default approximation margin."""
        return self.bounds().earliest

    @property
    def latest(self) -> dt.date | None:
        """The latest proleptic Gregorian day, with the default approximation margin."""
        return self.bounds().latest


def _to_date(jdn: int | None) -> dt.date | None:
    if jdn is None:
        return None
    try:
        return date_from_jdn(jdn)
    except (ValueError, OverflowError) as exc:
        raise DateBoundsError(
            f"JDN {jdn} is outside the datetime.date range (years 1 to 9999); use jdn_bounds()"
        ) from exc


def _check_order(first: CalendarDate, second: CalendarDate, kind: DateKind) -> None:
    try:
        first_lo = first.jdn_bounds()[0]
        second_hi = second.jdn_bounds()[1]
    except UnsupportedCalendarError:
        return
    if first_lo > second_hi:
        word = "AND" if kind is DateKind.BETWEEN else "TO"
        raise ValueError(
            f"the first date ({first.format()}) is after the {word} date ({second.format()})"
        )


def format_date_value(value: DateValue) -> str:
    """Return the canonical GEDCOM 7 text of `value` (the phrase is not part of it)."""
    first, second = value.first, value.second
    if first is None:
        return ""
    if value.kind is DateKind.DATE:
        return first.format()
    if second is not None:
        joiner = "AND" if value.kind is DateKind.BETWEEN else "TO"
        lead = "BET" if value.kind is DateKind.BETWEEN else "FROM"
        return f"{lead} {first.format()} {joiner} {second.format()}"
    return f"{value.kind.value} {first.format()}"
