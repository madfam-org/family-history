"""A forgiving parser for the dates Mexican families type, in Spanish.

It accepts what people write («15 de marzo de 1923», «15/03/1923», «marzo 1923», «c. 1890»,
«1890?», «antes de 1900», «entre 1890 y 1895», «de 1910 a 1920») and returns a GEDCOM 7
`DateValue`. It never guesses: input with more than one reasonable reading raises
`DateParseError` that says how to write it unambiguously. The documented conventions are:

- All-numeric dates are day/month/year, the es-MX order. A month above 12 is an error that
  suggests a month name; the parts are never swapped silently.
- Two-digit years are rejected (the century is unknown).
- «1890-1895» is rejected: it can mean «entre» (a range) or «de … a …» (a period).
- A weekday («lunes 15 de marzo de 1923») must match the date.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

from ._calendars import GREGORIAN_MONTHS, Calendar
from ._model import CalendarDate, DateKind, DateParseError, DateValue

__all__ = ["parse_user_date_es"]

_MONTHS: dict[str, int] = {
    "enero": 1, "ene": 1, "january": 1, "jan": 1,
    "febrero": 2, "feb": 2, "february": 2,
    "marzo": 3, "mar": 3, "march": 3,
    "abril": 4, "abr": 4, "april": 4, "apr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6, "june": 6,
    "julio": 7, "jul": 7, "july": 7,
    "agosto": 8, "ago": 8, "august": 8, "aug": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "sept": 9, "set": 9, "september": 9,
    "octubre": 10, "oct": 10, "october": 10,
    "noviembre": 11, "nov": 11, "november": 11,
    "diciembre": 12, "dic": 12, "december": 12, "dec": 12,
}  # fmt: skip

_WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")

# A bare word qualifier must be followed by a space, so «ca» never eats «calculado».
_APPROX = re.compile(
    r"^(?:c\.|ca\.|aprox\.|(?:ca|circa|cerca de|hacia(?: el)?|aprox|aproximadamente"
    r"|alrededor del?)(?=\s))\s*"
)
_CALC = re.compile(r"^(?:calc\.|calculado(?=\s))\s*")
_EST = re.compile(r"^(?:est\.|estimado(?=\s))\s*")
_SINGLE_PREFIXES: tuple[tuple[re.Pattern[str], DateKind], ...] = (
    (re.compile(r"^antes del?\s+"), DateKind.BEFORE),
    (re.compile(r"^despues del?\s+"), DateKind.AFTER),
    (re.compile(r"^(?:a partir del?|desde(?: el)?)\s+"), DateKind.FROM),
    (re.compile(r"^hasta(?: el)?\s+"), DateKind.TO),
)
_BCE = re.compile(r"\s*(?:a\.?\s*(?:de\s*)?c\.?|antes de cristo)$")
_CE = re.compile(r"\s*(?:d\.?\s*(?:de\s*)?c\.?|despues de cristo)$")
_JULIAN = re.compile(r"\s*\(?\s*(?:calendario\s+)?juliano\s*\)?$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})\2(\d+)$")
_MY = re.compile(r"^(\d{1,2})[/\-](\d+)$")
_YEAR_SPAN = re.compile(r"^\d+\s*[-–]\s*\d+$")
_DECADE = re.compile(r"^(?:(?:la\s+)?decada\s+de(?:\s+los)?|los\s+anos|anos)\s+(\d{4})$|^(\d{4})s$")
_ORDINAL = re.compile(r"^(\d{1,2})(?:o|ro|\.o)?$")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.replace("°", "o"))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def parse_user_date_es(text: str) -> DateValue:
    """Parse a date as typed by a Spanish-speaking user. `original` keeps the typed text.

    Raises `DateParseError` for empty, unrecognized or ambiguous input.
    """
    folded = _fold(text)
    if not folded:
        raise DateParseError("the date is empty", text)
    if folded.endswith("?"):
        body = folded[:-1].strip()
        if "?" in body or _has_qualifier(body):
            raise DateParseError("use «?» or a qualifier such as «hacia», not both", text)
        return DateValue(DateKind.ABOUT, _single(body, text), original=text)
    if "?" in folded:
        raise DateParseError("«?» is only understood at the end, as in «1890?»", text)
    decade = _DECADE.match(folded)
    if decade:
        start = int(decade.group(1) or decade.group(2))
        if start % 10:
            raise DateParseError(f"{start} does not start a decade", text)
        first, second = CalendarDate(start), CalendarDate(start + 9)
        return DateValue(DateKind.BETWEEN, first, second, original=text)
    for pattern, kind in ((_APPROX, DateKind.ABOUT), (_CALC, DateKind.CALCULATED),
                          (_EST, DateKind.ESTIMATED)):  # fmt: skip
        match = pattern.match(folded)
        if match:
            return DateValue(kind, _single(folded[match.end() :], text), original=text)
    if folded.startswith("entre "):
        parts = re.split(r"\s+y\s+", folded[len("entre ") :])
        if len(parts) != 2:
            raise DateParseError("write «entre <fecha> y <fecha>»", text)
        first, second = _single(parts[0], text), _single(parts[1], text)
        return _pair(DateKind.BETWEEN, first, second, text)
    period = _period(folded, text)
    if period is not None:
        return period
    for pattern, kind in _SINGLE_PREFIXES:
        match = pattern.match(folded)
        if match:
            return DateValue(kind, _single(folded[match.end() :], text), original=text)
    if _YEAR_SPAN.match(folded):
        raise DateParseError(
            "«1890-1895» is ambiguous: write «entre 1890 y 1895» or «de 1890 a 1895»",
            text,
            "ambiguous_date",
        )
    return DateValue(DateKind.DATE, _single(folded, text), original=text)


def _has_qualifier(body: str) -> bool:
    patterns = (_APPROX, _CALC, _EST, *(pattern for pattern, _ in _SINGLE_PREFIXES))
    return body.startswith("entre ") or any(p.match(body) for p in patterns)


def _period(folded: str, text: str) -> DateValue | None:
    if folded.startswith("desde ") and " hasta " in folded:
        left, right = folded[len("desde ") :].split(" hasta ", 1)
        right = right.removeprefix("el ")
    elif folded.startswith(("de ", "del ")):
        rest = folded.split(" ", 1)[1]
        parts = re.split(r"\s+al?\s+", rest)
        if len(parts) == 1:
            return None
        if len(parts) != 2:
            raise DateParseError("write «de <fecha> a <fecha>»", text)
        left, right = parts
    else:
        return None
    first, second = _single(left.removeprefix("el "), text), _single(right, text)
    return _pair(DateKind.FROM_TO, first, second, text)


def _pair(kind: DateKind, first: CalendarDate, second: CalendarDate, text: str) -> DateValue:
    try:
        return DateValue(kind, first, second, original=text)
    except ValueError as exc:
        raise DateParseError(str(exc), text) from exc


def _single(body: str, text: str) -> CalendarDate:
    body = body.strip().removeprefix("el ").strip()
    calendar = Calendar.GREGORIAN
    julian = _JULIAN.search(body)
    if julian:
        calendar = Calendar.JULIAN
        body = body[: julian.start()].strip()
    bce = False
    bce_match = _BCE.search(body)
    if bce_match and bce_match.start() > 0:
        bce = True
        body = body[: bce_match.start()].strip()
    else:
        ce_match = _CE.search(body)
        if ce_match and ce_match.start() > 0:
            body = body[: ce_match.start()].strip()
    weekday: int | None = None
    head = body.split(" ", 1)[0].rstrip(",")
    if head in _WEEKDAYS:
        weekday = _WEEKDAYS.index(head)
        body = body[len(head) :].lstrip(", ").strip()
    if not body:
        raise DateParseError("a date is missing", text)
    year, month, day = _ymd(body, text, allow_short_year=bce)
    try:
        value = CalendarDate(
            year=year,
            month=GREGORIAN_MONTHS[month - 1] if month else None,
            day=day,
            calendar=calendar,
            bce=bce,
        )
    except ValueError as exc:
        raise DateParseError(str(exc), text) from exc
    if weekday is not None:
        _check_weekday(value, weekday, text)
    return value


def _ymd(body: str, text: str, *, allow_short_year: bool) -> tuple[int, int | None, int | None]:
    iso = _ISO.match(body)
    if iso:
        return int(iso.group(1)), _month(int(iso.group(2)), text), int(iso.group(3))
    dmy = _DMY.match(body)
    if dmy:
        day, month, year = int(dmy.group(1)), int(dmy.group(3)), dmy.group(4)
        if month > 12:
            raise DateParseError(
                f"month {month} does not exist; numeric dates are day/month/year. "
                "Write the month name, e.g. «15 de marzo de 1923»",
                text,
                "ambiguous_date",
            )
        return _year(year, text, allow_short_year), _month(month, text), day
    month_year = _MY.match(body)
    if month_year:
        month = _month(int(month_year.group(1)), text)
        return _year(month_year.group(2), text, allow_short_year), month, None
    words = [tok.rstrip(".") for tok in re.sub(r"[,/\-]", " ", body).split()]
    words = [tok for tok in words if tok not in ("de", "del")]
    numbers: list[str] = []
    months: list[int] = []
    shape: list[str] = []
    for word in words:
        if word == "primero":
            numbers.append("1")
            shape.append("n")
        elif word in _MONTHS:
            months.append(_MONTHS[word])
            shape.append("m")
        elif _ORDINAL.match(word) or word.isdigit():
            ordinal = _ORDINAL.match(word)
            numbers.append(ordinal.group(1) if ordinal else word)
            shape.append("n")
        else:
            raise DateParseError(f"unrecognized word {word!r}", text)
    pattern = "".join(shape)
    if pattern == "n":
        return _year(numbers[0], text, allow_short_year), None, None
    if pattern == "mn":
        return _year(numbers[0], text, allow_short_year), months[0], None
    if pattern == "nmn":
        return _year(numbers[1], text, allow_short_year), months[0], int(numbers[0])
    if pattern == "mnn":
        return _year(numbers[1], text, allow_short_year), months[0], int(numbers[0])
    raise DateParseError(
        "write a date like «15 de marzo de 1923», «marzo de 1923» or «1923»", text
    )


def _year(token: str, text: str, allow_short: bool) -> int:
    if not token.isdigit():
        raise DateParseError(f"year {token!r} must be digits", text)
    if len(token) > 4:
        raise DateParseError(f"year {token} has too many digits", text)
    if len(token) < 3 and not allow_short:
        raise DateParseError(
            f"the year «{token}» is ambiguous (which century?); write all four digits",
            text,
            "ambiguous_date",
        )
    return int(token)


def _month(month: int, text: str) -> int:
    if not 1 <= month <= 12:
        raise DateParseError(f"month {month} does not exist", text)
    return month


def _check_weekday(value: CalendarDate, weekday: int, text: str) -> None:
    if value.day is None or value.month_number is None:
        raise DateParseError("a weekday needs a full date", text)
    if value.calendar is not Calendar.GREGORIAN or value.bce:
        raise DateParseError("weekdays are only checked for Gregorian CE dates", text)
    actual = dt.date(value.year, value.month_number, value.day).weekday()
    if actual != weekday:
        raise DateParseError(
            f"that date was a {_WEEKDAYS[actual]}, not a {_WEEKDAYS[weekday]}", text
        )
