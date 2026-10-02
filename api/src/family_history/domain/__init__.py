"""Pure genealogy domain library: stdlib only, no I/O.

The public API is re-exported here; submodules hold the detail.
"""

from .dates import (
    Calendar,
    CalendarDate,
    DateBounds,
    DateBoundsError,
    DateKind,
    DateParseError,
    DateValue,
    UnsupportedCalendarError,
    canonicalize_date_value,
    format_date_value,
    humanize_en,
    humanize_es,
    parse_date_value,
    parse_user_date_es,
)

__all__ = [
    "Calendar",
    "CalendarDate",
    "DateBounds",
    "DateBoundsError",
    "DateKind",
    "DateParseError",
    "DateValue",
    "UnsupportedCalendarError",
    "canonicalize_date_value",
    "format_date_value",
    "humanize_en",
    "humanize_es",
    "parse_date_value",
    "parse_user_date_es",
]
