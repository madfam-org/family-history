"""Parser for the GEDCOM 7.0 `DateValue` grammar.

```
DateValue  = [ date / DatePeriod / dateRange / dateApprox ]
DatePeriod = [ "TO" D date ] / "FROM" D date [ D "TO" D date ]
dateRange  = "BET" D date D "AND" D date / "AFT" D date / "BEF" D date
dateApprox = ("ABT" / "CAL" / "EST") D date
date       = [calendar D] [[day D] month D] year [D epoch]
```

The parser is lenient about letter case and runs of spaces, and strict about everything else.
`format_date_value(parse_date_value(s))` is the canonical spelling of `s`: upper-case keywords,
single spaces, no leading zeros, and no explicit `GREGORIAN` (it is the default calendar).
Extension calendars, months and epochs (`_TAG`) are rejected with a clear error.
"""

from __future__ import annotations

import re

from ._calendars import Calendar, months_for
from ._model import CalendarDate, DateKind, DateParseError, DateValue, format_date_value

__all__ = ["canonicalize_date_value", "parse_calendar_date", "parse_date_value"]

_DUAL_YEAR = re.compile(r"^\d+/\d{1,2}$")

_SINGLE_KEYWORDS: dict[str, DateKind] = {
    "ABT": DateKind.ABOUT,
    "CAL": DateKind.CALCULATED,
    "EST": DateKind.ESTIMATED,
    "BEF": DateKind.BEFORE,
    "AFT": DateKind.AFTER,
    "TO": DateKind.TO,
}

_GEDCOM5_HINTS: dict[str, str] = {
    "INT": "INT (interpreted dates) is GEDCOM 5.5.1; GEDCOM 7 puts the text in a PHRASE",
    "ABOUT": "write ABT, not ABOUT",
    "ABT.": "write ABT without a period",
    "BEFORE": "write BEF, not BEFORE",
    "AFTER": "write AFT, not AFTER",
    "BETWEEN": "write BET, not BETWEEN",
    "B.C.": "write BCE, not B.C.",
    "BC": "write BCE, not BC",
}


def parse_date_value(text: str, phrase: str | None = None) -> DateValue:
    """Parse GEDCOM 7 date text into a `DateValue`.

    The empty string is the valid empty date value. `phrase` is the optional GEDCOM `PHRASE`
    substructure and is stored as given. Raises `DateParseError` with a reason when `text` does
    not match the grammar.
    """
    tokens = text.split()
    clean_phrase = phrase if phrase is None or phrase.strip() else None
    if not tokens:
        return DateValue(DateKind.EMPTY, phrase=clean_phrase, original=text)
    head = tokens[0].upper()
    try:
        if head in _SINGLE_KEYWORDS:
            kind = _SINGLE_KEYWORDS[head]
            first = _parse_date_tokens(tokens[1:], text, head)
            return DateValue(kind, first, phrase=clean_phrase, original=text)
        if head == "BET":
            start, end = _split_pair(tokens[1:], "AND", text, "BET")
            return DateValue(DateKind.BETWEEN, start, end, phrase=clean_phrase, original=text)
        if head == "FROM":
            rest = tokens[1:]
            if any(token.upper() == "TO" for token in rest):
                start, end = _split_pair(rest, "TO", text, "FROM")
                return DateValue(DateKind.FROM_TO, start, end, phrase=clean_phrase, original=text)
            first = _parse_date_tokens(rest, text, "FROM")
            return DateValue(DateKind.FROM, first, phrase=clean_phrase, original=text)
        if head == "AND":
            raise DateParseError("AND is only valid after BET x", text)
        first = _parse_date_tokens(tokens, text, None)
        return DateValue(DateKind.DATE, first, phrase=clean_phrase, original=text)
    except DateParseError:
        raise
    except ValueError as exc:
        raise DateParseError(str(exc), text) from exc


def canonicalize_date_value(text: str) -> str:
    """Return the canonical GEDCOM 7 spelling of `text` (raises `DateParseError`)."""
    return format_date_value(parse_date_value(text))


def parse_calendar_date(text: str) -> CalendarDate:
    """Parse a single GEDCOM 7 `date` (no keywords) such as `JULIAN 11 FEB 1732`."""
    return _parse_date_tokens(text.split(), text, None)


def _split_pair(
    tokens: list[str], joiner: str, text: str, lead: str
) -> tuple[CalendarDate, CalendarDate]:
    positions = [i for i, token in enumerate(tokens) if token.upper() == joiner]
    if len(positions) != 1:
        raise DateParseError(f"{lead} needs exactly one {joiner}: {lead} x {joiner} y", text)
    cut = positions[0]
    start = _parse_date_tokens(tokens[:cut], text, lead)
    end = _parse_date_tokens(tokens[cut + 1 :], text, joiner)
    return start, end


def _parse_date_tokens(tokens: list[str], text: str, after: str | None) -> CalendarDate:
    if not tokens:
        where = f"after {after}" if after else "here"
        raise DateParseError(f"a date is missing {where}", text)
    for token in tokens:
        hint = _GEDCOM5_HINTS.get(token.upper())
        if hint:
            raise DateParseError(hint, text)
        if token.startswith("@#"):
            raise DateParseError(
                "calendar escapes like @#DJULIAN@ are GEDCOM 5.5.1; GEDCOM 7 writes JULIAN", text
            )
        if token.startswith("("):
            raise DateParseError("free text in parentheses belongs in the PHRASE", text)
    rest = list(tokens)
    calendar = Calendar.GREGORIAN
    head = rest[0].upper()
    if head in Calendar.__members__:
        calendar = Calendar(head)
        rest.pop(0)
    elif head.startswith("_"):
        raise DateParseError(f"extension calendar {rest[0]!r} is not supported", text)
    bce = False
    if rest and rest[-1].upper() == "BCE":
        bce = True
        rest.pop()
    elif rest and rest[-1].startswith("_"):
        raise DateParseError(f"extension epoch {rest[-1]!r} is not supported", text)
    if not rest:
        raise DateParseError("a date needs a year", text)
    if len(rest) > 3:
        raise DateParseError(
            f"unexpected words {' '.join(rest[:-3])!r}; a date is [calendar] [[day] month] year",
            text,
        )
    year = _parse_int(rest[-1], "year", text)
    month: str | None = None
    day: int | None = None
    if len(rest) >= 2:
        month = rest[-2].upper()
        if month not in months_for(calendar):
            raise DateParseError(
                f"{rest[-2]!r} is not a {calendar.value} month "
                f"(expected one of {', '.join(months_for(calendar))})",
                text,
            )
    if len(rest) == 3:
        day = _parse_int(rest[0], "day", text)
    try:
        return CalendarDate(year=year, month=month, day=day, calendar=calendar, bce=bce)
    except ValueError as exc:
        raise DateParseError(str(exc), text) from exc


def _parse_int(token: str, what: str, text: str) -> int:
    if what == "year" and _DUAL_YEAR.match(token):
        raise DateParseError(
            f"dual year {token!r} is GEDCOM 5.5.1; GEDCOM 7 writes the JULIAN date instead", text
        )
    if not token.isascii() or not token.isdigit():
        raise DateParseError(f"{what} {token!r} must be digits", text)
    return int(token)
