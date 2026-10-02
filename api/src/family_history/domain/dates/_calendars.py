"""Calendar tables and day arithmetic for the GEDCOM 7 calendars.

Days are counted as Julian Day Numbers (JDN): an integer that names the same day in every
calendar and keeps working before year 1, where `datetime.date` cannot go. Years are passed in
astronomical numbering (1 BCE is year 0, 2 BCE is year -1) so the leap-year rules stay uniform.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

__all__ = [
    "Calendar",
    "FRENCH_R_MONTHS",
    "GREGORIAN_MONTHS",
    "HEBREW_MONTHS",
    "JULIAN_MONTHS",
    "date_from_jdn",
    "days_in_month",
    "gregorian_to_jdn",
    "jdn_from_date",
    "julian_to_jdn",
    "months_for",
]


class Calendar(StrEnum):
    """The four calendars defined by GEDCOM 7.0."""

    GREGORIAN = "GREGORIAN"
    JULIAN = "JULIAN"
    FRENCH_R = "FRENCH_R"
    HEBREW = "HEBREW"


GREGORIAN_MONTHS: tuple[str, ...] = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)
JULIAN_MONTHS: tuple[str, ...] = GREGORIAN_MONTHS
FRENCH_R_MONTHS: tuple[str, ...] = (
    "VEND",
    "BRUM",
    "FRIM",
    "NIVO",
    "PLUV",
    "VENT",
    "GERM",
    "FLOR",
    "PRAI",
    "MESS",
    "THER",
    "FRUC",
    "COMP",
)
HEBREW_MONTHS: tuple[str, ...] = (
    "TSH",
    "CSH",
    "KSL",
    "TVT",
    "SHV",
    "ADR",
    "ADS",
    "NSN",
    "IYR",
    "SVN",
    "TMZ",
    "AAV",
    "ELL",
)

_MONTHS: dict[Calendar, tuple[str, ...]] = {
    Calendar.GREGORIAN: GREGORIAN_MONTHS,
    Calendar.JULIAN: JULIAN_MONTHS,
    Calendar.FRENCH_R: FRENCH_R_MONTHS,
    Calendar.HEBREW: HEBREW_MONTHS,
}

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Proleptic Gregorian ordinal 1 (0001-01-01) is JDN 1721426.
_ORDINAL_OFFSET = 1721425


def months_for(calendar: Calendar) -> tuple[str, ...]:
    """Return the GEDCOM month tags of `calendar`, in calendar order."""
    return _MONTHS[calendar]


def _is_leap(calendar: Calendar, astro_year: int) -> bool:
    if calendar is Calendar.JULIAN:
        return astro_year % 4 == 0
    return astro_year % 4 == 0 and (astro_year % 100 != 0 or astro_year % 400 == 0)


def days_in_month(calendar: Calendar, astro_year: int, month: int) -> int:
    """Return the maximum day number of `month` (1-based) in `calendar`.

    For the French Republican and Hebrew calendars this is the widest value the month can take
    in any year (30, or 6 for the complementary days), because exact year lengths there depend
    on rules this library does not compute.
    """
    if calendar in (Calendar.GREGORIAN, Calendar.JULIAN):
        if month == 2 and _is_leap(calendar, astro_year):
            return 29
        return _DAYS_IN_MONTH[month - 1]
    if calendar is Calendar.FRENCH_R:
        return 6 if month == 13 else 30
    return 30


def julian_to_jdn(astro_year: int, month: int, day: int) -> int:
    """Return the JDN of a Julian-calendar date."""
    a = (14 - month) // 12
    y = astro_year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083


def gregorian_to_jdn(astro_year: int, month: int, day: int) -> int:
    """Return the JDN of a proleptic Gregorian date."""
    a = (14 - month) // 12
    y = astro_year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def date_from_jdn(jdn: int) -> dt.date:
    """Return the proleptic Gregorian `datetime.date` for `jdn`.

    Raises `ValueError` when the day falls outside `datetime.date` (years 1 to 9999).
    """
    return dt.date.fromordinal(jdn - _ORDINAL_OFFSET)


def jdn_from_date(value: dt.date) -> int:
    """Return the JDN of a proleptic Gregorian `datetime.date`."""
    return value.toordinal() + _ORDINAL_OFFSET
