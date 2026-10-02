"""Convert GEDCOM 5.5.1 DATE payloads to the 7.0 date grammar, syntactically.

What changes, and how the original is kept:

* calendar escapes ``@#DJULIAN@`` -> ``JULIAN`` (also HEBREW, ``FRENCH R`` -> ``FRENCH_R``;
  ``@#DGREGORIAN@`` is dropped because Gregorian is the default);
* ``B.C.`` -> ``BCE``;
* dual years ``1750/51`` -> the new-style year ``1751``, with the original text in a PHRASE
  (the form Appendix A of the 7.0 specification recommends);
* ``INT <date> (<text>)`` -> ``<date>`` plus a PHRASE with the text, and ``(<text>)`` -> an
  empty date plus a PHRASE;
* common vendor spellings (``Abt.``, ``about``, ``circa``, ``bet. ... and``, lower-case or
  full or Spanish month names, ISO ``YYYY-MM-DD``) are normalized; the import report lists
  each one;
* anything still not matching the 7.0 grammar becomes an empty date with the original text as
  PHRASE, so nothing is lost.

Only syntax is touched; no calendar arithmetic happens here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from family_history.gedcom.datatypes import is_date_value

_ESCAPES = {
    "@#DGREGORIAN@": "",
    "@#DJULIAN@": "JULIAN",
    "@#DHEBREW@": "HEBREW",
    "@#DFRENCH R@": "FRENCH_R",
}
_UNSUPPORTED_ESCAPES = ("@#DROMAN@", "@#DUNKNOWN@")

_KEYWORDS = {
    "ABT": "ABT", "ABT.": "ABT", "ABOUT": "ABT", "CIRCA": "ABT", "CA": "ABT", "CA.": "ABT",
    "C.": "ABT", "APROX": "ABT", "APROX.": "ABT", "EST": "EST", "EST.": "EST",
    "CAL": "CAL", "CAL.": "CAL", "BEF": "BEF", "BEF.": "BEF", "BEFORE": "BEF", "AFT": "AFT",
    "AFT.": "AFT", "AFTER": "AFT", "BET": "BET", "BET.": "BET", "BETWEEN": "BET",
    "AND": "AND", "FROM": "FROM", "TO": "TO",
}
_MONTHS = {
    "JANUARY": "JAN", "FEBRUARY": "FEB", "MARCH": "MAR", "APRIL": "APR", "JUNE": "JUN",
    "JULY": "JUL", "AUGUST": "AUG", "SEPTEMBER": "SEP", "SEPT": "SEP", "OCTOBER": "OCT",
    "NOVEMBER": "NOV", "DECEMBER": "DEC",
    "ENE": "JAN", "ENERO": "JAN", "FEBRERO": "FEB", "MARZO": "MAR", "ABR": "APR",
    "ABRIL": "APR", "MAYO": "MAY", "JUNIO": "JUN", "JULIO": "JUL", "AGO": "AUG",
    "AGOSTO": "AUG", "SEPTIEMBRE": "SEP", "SETIEMBRE": "SEP", "OCTUBRE": "OCT",
    "NOVIEMBRE": "NOV", "DIC": "DEC", "DICIEMBRE": "DEC",
}
_GREGORIAN = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
_DUAL_RE = re.compile(r"^(\d{3,4})/(\d{1,4})$")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_INT_RE = re.compile(r"^INT (.*?) ?\((.*)\)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class DateUpgrade:
    """The 7.0 payload, an optional PHRASE, and a note when anything changed.

    ``interpretive`` is true when the change involved a judgement (a dual year was resolved, an
    unreadable date was moved to PHRASE) rather than a pure spelling normalization.
    """

    value: str
    phrase: str | None = None
    note: str | None = None
    interpretive: bool = False


def upgrade_date(original: str) -> DateUpgrade:
    """Upgrade one 5.5.1 DATE payload. Never raises."""
    text = " ".join(original.split())
    if text == "":
        return DateUpgrade("")
    if text.startswith("(") and text.endswith(")"):
        return DateUpgrade("", text[1:-1].strip(), "date phrase moved to PHRASE", True)
    match = _INT_RE.match(text) or _INT_RE.match(text.upper()[:4] + text[4:])
    if match is not None:
        inner = upgrade_date(match.group(1))
        phrase = match.group(2).strip() or original
        if inner.phrase is not None:
            phrase = f"{phrase} ({inner.phrase})"
        return DateUpgrade(
            inner.value, phrase, "interpreted date (INT) phrase moved to PHRASE", True
        )
    if any(escape in text.upper() for escape in _UNSUPPORTED_ESCAPES):
        return DateUpgrade(
            "", original, "calendar not supported by GEDCOM 7.0; kept as PHRASE", True
        )
    converted, dual = _convert_tokens(text)
    if converted is not None and is_date_value(converted):
        if dual:
            return DateUpgrade(
                converted, original, "dual year resolved to the new-style year", True
            )
        if converted != text:
            return DateUpgrade(converted, None, f"normalized from {original!r}")
        return DateUpgrade(converted)
    return DateUpgrade("", original, "not a valid date; original kept as PHRASE", True)


def _convert_tokens(text: str) -> tuple[str | None, bool]:
    upper = text.upper()
    for escape, calendar in _ESCAPES.items():
        upper = upper.replace(escape, f" {calendar} " if calendar else " ")
    upper = upper.replace("B.C.", "BCE").replace("(BCE)", "BCE")
    tokens = upper.split()
    result: list[str] = []
    dual = False
    for token in tokens:
        if token in _KEYWORDS:
            result.append(_KEYWORDS[token])
            continue
        if token in _MONTHS:
            result.append(_MONTHS[token])
            continue
        if token in ("BC", "B.C"):
            result.append("BCE")
            continue
        iso = _ISO_RE.match(token)
        if iso is not None:
            month = int(iso.group(2))
            if not 1 <= month <= 12:
                return None, False
            result.extend([str(int(iso.group(3))), _GREGORIAN[month - 1], iso.group(1)])
            continue
        dual_match = _DUAL_RE.match(token)
        if dual_match is not None:
            year = _new_style_year(dual_match.group(1), dual_match.group(2))
            if year is None:
                return None, False
            result.append(year)
            dual = True
            continue
        if token.endswith(",") and token[:-1].isdigit():
            token = token[:-1]
        result.append(token.lstrip("0") if token.isdigit() and token.strip("0") else token)
    return " ".join(result), dual


def _new_style_year(first: str, second: str) -> str | None:
    """``1750/51`` -> ``1751``; ``1699/00`` -> ``1700``; ``1750/1751`` -> ``1751``."""
    year = int(first) + 1
    rendered = str(year)
    if rendered.endswith(second) or rendered[-len(second) :] == second.zfill(len(second)):
        return rendered
    return None
