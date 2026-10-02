"""Syntactic checks for GEDCOM 7.0 payload data types.

These functions answer one question: does a payload string match its data type's grammar?
They never interpret meaning. In particular, DATE payloads stay strings everywhere in this
package; semantic date handling (calendars, ranges, sorting) belongs to the domain layer.
"""

from __future__ import annotations

import re

STD_TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
EXT_TAG_RE = re.compile(r"^_[A-Z0-9_]+$")
INTEGER_RE = re.compile(r"^[0-9]+$")
TIME_RE = re.compile(r"^(?:[01]?[0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.[0-9]+)?)?Z?$")
AGE_RE = re.compile(
    r"^(?:[<>] )?(?:"
    r"[0-9]+y(?: [0-9]+m)?(?: [0-9]+w)?(?: [0-9]+d)?"
    r"|[0-9]+m(?: [0-9]+w)?(?: [0-9]+d)?"
    r"|[0-9]+w(?: [0-9]+d)?"
    r"|[0-9]+d)$"
)
LATITUDE_RE = re.compile(r"^[NS](?:90|[0-8]?[0-9])(?:\.[0-9]+)?$")
LONGITUDE_RE = re.compile(r"^[EW](?:180|1[0-7][0-9]|0?[0-9]?[0-9])(?:\.[0-9]+)?$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_MEDIA_CHARS = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
MEDIA_TYPE_RE = re.compile(
    rf"^{_MEDIA_CHARS}/{_MEDIA_CHARS}"
    rf"(?:[ \t]*;[ \t]*{_MEDIA_CHARS}=(?:{_MEDIA_CHARS}|\"[^\"]*\"))*$"
)
URI_RE = re.compile(r"^[^\s<>\"{}|\\^`]+$")
LIST_DELIM_RE = re.compile(r" *, *")

CALENDARS = frozenset({"GREGORIAN", "JULIAN", "FRENCH_R", "HEBREW"})
GREGORIAN_MONTHS = frozenset("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())
MONTHS: dict[str, frozenset[str]] = {
    "GREGORIAN": GREGORIAN_MONTHS,
    "JULIAN": GREGORIAN_MONTHS,
    "FRENCH_R": frozenset(
        "VEND BRUM FRIM NIVO PLUV VENT GERM FLOR PRAI MESS THER FRUC COMP".split()
    ),
    "HEBREW": frozenset("TSH CSH KSL TVT SHV ADR ADS NSN IYR SVN TMZ AAV ELL".split()),
}
EPOCHS: dict[str, frozenset[str]] = {
    "GREGORIAN": frozenset({"BCE"}),
    "JULIAN": frozenset({"BCE"}),
    "FRENCH_R": frozenset(),
    "HEBREW": frozenset(),
}
DATE_KEYWORDS = frozenset({"FROM", "TO", "BET", "AND", "BEF", "AFT", "ABT", "CAL", "EST"})


def is_enum(value: str) -> bool:
    return bool(STD_TAG_RE.match(value) or EXT_TAG_RE.match(value) or INTEGER_RE.match(value))


def split_list(value: str) -> list[str]:
    """Split a ``List`` payload on commas with any surrounding spaces."""
    return LIST_DELIM_RE.split(value)


def is_date(value: str) -> bool:
    """The ``date`` production: ``[calendar D] [[day D] month D] year [D epoch]``."""
    tokens = value.split(" ")
    if "" in tokens:
        return False
    calendar = "GREGORIAN"
    if tokens[0] in CALENDARS or (EXT_TAG_RE.match(tokens[0]) and len(tokens) > 1):
        calendar = tokens.pop(0)
    extension = calendar not in CALENDARS
    if len(tokens) >= 2 and not INTEGER_RE.match(tokens[-1]) and INTEGER_RE.match(tokens[-2]):
        epoch = tokens.pop()
        if extension:
            allowed = epoch == "BCE" or bool(EXT_TAG_RE.match(epoch))
        else:
            allowed = epoch in EPOCHS[calendar] or bool(EXT_TAG_RE.match(epoch))
        if not allowed:
            return False
    return _day_month_year(tokens, calendar, extension)


def _day_month_year(tokens: list[str], calendar: str, extension: bool) -> bool:
    if not tokens or len(tokens) > 3 or not INTEGER_RE.match(tokens[-1]):
        return False
    if len(tokens) == 1:
        return True
    month = tokens[-2]
    if extension:
        month_ok = bool(STD_TAG_RE.match(month) or EXT_TAG_RE.match(month))
    else:
        month_ok = month in MONTHS[calendar] or bool(EXT_TAG_RE.match(month))
    if not month_ok or month in DATE_KEYWORDS:
        return False
    if len(tokens) == 3:
        day = tokens[0]
        return bool(INTEGER_RE.match(day)) and 1 <= int(day) <= 36
    return True


def is_date_period(value: str) -> bool:
    if value == "":
        return True
    if value.startswith("TO "):
        return is_date(value[3:])
    if value.startswith("FROM "):
        rest = value[5:]
        if " TO " in rest:
            start, _, end = rest.partition(" TO ")
            return is_date(start) and is_date(end)
        return is_date(rest)
    return False


def is_date_value(value: str) -> bool:
    """The ``DateValue`` production (the empty string included)."""
    if value == "" or is_date(value) or is_date_period(value):
        return True
    head, _, rest = value.partition(" ")
    if head == "BET" and " AND " in rest:
        start, _, end = rest.partition(" AND ")
        return is_date(start) and is_date(end)
    if head in ("AFT", "BEF", "ABT", "CAL", "EST"):
        return is_date(rest)
    return False


def is_date_exact(value: str) -> bool:
    tokens = value.split(" ")
    return (
        len(tokens) == 3
        and bool(INTEGER_RE.match(tokens[0]))
        and 1 <= int(tokens[0]) <= 31
        and tokens[1] in GREGORIAN_MONTHS
        and bool(INTEGER_RE.match(tokens[2]))
    )


def is_personal_name(value: str) -> bool:
    if "\t" in value or "\n" in value:
        return False
    return value.count("/") in (0, 2)


def is_tag_def(value: str) -> bool:
    tag, _, uri = value.partition(" ")
    return bool(EXT_TAG_RE.match(tag)) and bool(uri) and bool(URI_RE.match(uri))


def is_file_path(value: str) -> bool:
    return value != "" and not any(ch in value for ch in " \t\\\"<>") and "\n" not in value


_CHECKS = {
    "Integer": lambda v: bool(INTEGER_RE.match(v)),
    "DateValue": is_date_value,
    "DatePeriod": is_date_period,
    "DateExact": is_date_exact,
    "Time": lambda v: bool(TIME_RE.match(v)),
    "Age": lambda v: v == "" or bool(AGE_RE.match(v)),
    "Language": lambda v: bool(LANGUAGE_RE.match(v)),
    "MediaType": lambda v: bool(MEDIA_TYPE_RE.match(v)),
    "Latitude": lambda v: bool(LATITUDE_RE.match(v)),
    "Longitude": lambda v: bool(LONGITUDE_RE.match(v)),
    "PersonalName": is_personal_name,
    "TagDef": is_tag_def,
    "URI": lambda v: bool(URI_RE.match(v)),
    "FilePath": is_file_path,
}

_SINGLE_LINE = frozenset(_CHECKS) | {"Enum", "List:Enum", "List:Text"}


def check_value(datatype: str, value: str, enum_set: frozenset[str] | None = None) -> str | None:
    """Return a problem description when ``value`` does not match ``datatype``, else ``None``.

    ``Text`` and ``Special`` accept anything. Enumerations accept the standard values in
    ``enum_set`` plus any extension tag.
    """
    if datatype in ("Text", "Special"):
        return None
    if "\n" in value and datatype in _SINGLE_LINE:
        return f"{datatype} payload cannot span several lines"
    if datatype == "Enum":
        return _check_enum(value, enum_set)
    if datatype == "List:Enum":
        for item in split_list(value):
            problem = _check_enum(item, enum_set)
            if problem is not None:
                return problem
        return None
    if datatype == "List:Text":
        return None
    check = _CHECKS.get(datatype)
    if check is None or check(value):
        return None
    return f"{value!r} is not a valid {datatype}"


def _check_enum(value: str, enum_set: frozenset[str] | None) -> str | None:
    if EXT_TAG_RE.match(value):
        return None
    if not is_enum(value):
        return f"{value!r} is not an enumeration value"
    if enum_set is not None and value not in enum_set:
        return f"{value!r} is not one of the permitted values"
    return None
