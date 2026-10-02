"""Human-readable rendering of `DateValue` in Spanish (es-MX) and English."""

from __future__ import annotations

from ._calendars import Calendar
from ._model import CalendarDate, DateKind, DateValue

__all__ = ["MONTH_NAMES_EN", "MONTH_NAMES_ES", "humanize_en", "humanize_es"]

MONTH_NAMES_ES: dict[str, str] = {
    "JAN": "enero",
    "FEB": "febrero",
    "MAR": "marzo",
    "APR": "abril",
    "MAY": "mayo",
    "JUN": "junio",
    "JUL": "julio",
    "AUG": "agosto",
    "SEP": "septiembre",
    "OCT": "octubre",
    "NOV": "noviembre",
    "DEC": "diciembre",
    "VEND": "vendimiario",
    "BRUM": "brumario",
    "FRIM": "frimario",
    "NIVO": "nivoso",
    "PLUV": "pluvioso",
    "VENT": "ventoso",
    "GERM": "germinal",
    "FLOR": "floreal",
    "PRAI": "pradial",
    "MESS": "mesidor",
    "THER": "termidor",
    "FRUC": "fructidor",
    "COMP": "días complementarios",
    "TSH": "tishréi",
    "CSH": "jeshván",
    "KSL": "kislev",
    "TVT": "tevet",
    "SHV": "shevat",
    "ADR": "adar",
    "ADS": "adar II",
    "NSN": "nisán",
    "IYR": "iyar",
    "SVN": "siván",
    "TMZ": "tamuz",
    "AAV": "av",
    "ELL": "elul",
}

MONTH_NAMES_EN: dict[str, str] = {
    "JAN": "January",
    "FEB": "February",
    "MAR": "March",
    "APR": "April",
    "MAY": "May",
    "JUN": "June",
    "JUL": "July",
    "AUG": "August",
    "SEP": "September",
    "OCT": "October",
    "NOV": "November",
    "DEC": "December",
    "VEND": "Vendémiaire",
    "BRUM": "Brumaire",
    "FRIM": "Frimaire",
    "NIVO": "Nivôse",
    "PLUV": "Pluviôse",
    "VENT": "Ventôse",
    "GERM": "Germinal",
    "FLOR": "Floréal",
    "PRAI": "Prairial",
    "MESS": "Messidor",
    "THER": "Thermidor",
    "FRUC": "Fructidor",
    "COMP": "complementary days",
    "TSH": "Tishrei",
    "CSH": "Cheshvan",
    "KSL": "Kislev",
    "TVT": "Tevet",
    "SHV": "Shevat",
    "ADR": "Adar",
    "ADS": "Adar II",
    "NSN": "Nisan",
    "IYR": "Iyar",
    "SVN": "Sivan",
    "TMZ": "Tammuz",
    "AAV": "Av",
    "ELL": "Elul",
}

_CALENDAR_ES = {
    Calendar.JULIAN: "calendario juliano",
    Calendar.FRENCH_R: "calendario republicano francés",
    Calendar.HEBREW: "calendario hebreo",
}
_CALENDAR_EN = {
    Calendar.JULIAN: "Julian calendar",
    Calendar.FRENCH_R: "French Republican calendar",
    Calendar.HEBREW: "Hebrew calendar",
}


def _date_es(value: CalendarDate) -> str:
    year = f"{value.year} a. C." if value.bce else str(value.year)
    if value.month is None:
        text = year
    else:
        month = MONTH_NAMES_ES[value.month]
        text = f"{month} de {year}"
        if value.day is not None:
            text = f"{value.day} de {text}"
    if value.calendar in _CALENDAR_ES:
        text = f"{text} ({_CALENDAR_ES[value.calendar]})"
    return text


def _date_en(value: CalendarDate) -> str:
    year = f"{value.year} BCE" if value.bce else str(value.year)
    if value.month is None:
        text = year
    else:
        text = f"{MONTH_NAMES_EN[value.month]} {year}"
        if value.day is not None:
            text = f"{value.day} {text}"
    if value.calendar in _CALENDAR_EN:
        text = f"{text} ({_CALENDAR_EN[value.calendar]})"
    return text


def _with_article(preposition: str, value: CalendarDate) -> str:
    """Spanish needs «el» before a full date: «antes del 15 de marzo», «entre el 1 de …».

    `preposition` may be empty (no preposition, just the article when a day is present).
    """
    text = _date_es(value)
    if value.day is None:
        return f"{preposition} {text}".strip()
    if preposition == "de" or preposition.endswith(" de"):
        return f"{preposition}l {text}"
    if preposition == "a":
        return f"al {text}"
    return f"{preposition} el {text}".strip()


_WORDS_ES = {
    DateKind.ABOUT: "hacia",
    DateKind.BEFORE: "antes de",
    DateKind.AFTER: "después de",
    DateKind.FROM: "desde",
    DateKind.TO: "hasta",
}
_LABEL_ES = {DateKind.CALCULATED: "calculado", DateKind.ESTIMATED: "estimado"}
_PREFIX_EN = {
    DateKind.ABOUT: "about",
    DateKind.CALCULATED: "calculated",
    DateKind.ESTIMATED: "estimated",
    DateKind.BEFORE: "before",
    DateKind.AFTER: "after",
    DateKind.FROM: "from",
    DateKind.TO: "until",
}


def humanize_es(value: DateValue, *, include_phrase: bool = False) -> str:
    """Render `value` for Spanish readers, e.g. «15 de marzo de 1923», «hacia 1891».

    The empty date value renders as its phrase, or «fecha desconocida». With `include_phrase`,
    a phrase on a non-empty date is appended in «comillas».
    """
    first, second = value.first, value.second
    if first is None:
        return value.phrase or "fecha desconocida"
    if second is not None:
        if value.kind is DateKind.BETWEEN:
            text = f"{_with_article('entre', first)} y {_with_article('', second)}"
        else:
            text = f"{_with_article('de', first)} {_with_article('a', second)}"
    elif value.kind in _WORDS_ES:
        text = _with_article(_WORDS_ES[value.kind], first)
    elif value.kind in _LABEL_ES:
        text = f"{_LABEL_ES[value.kind]} {_date_es(first)}"
    else:
        text = _date_es(first)
    if include_phrase and value.phrase:
        text = f"{text} («{value.phrase}»)"
    return text


def humanize_en(value: DateValue, *, include_phrase: bool = False) -> str:
    """Render `value` for English readers, e.g. "15 March 1923", "about 1891"."""
    first, second = value.first, value.second
    if first is None:
        return value.phrase or "unknown date"
    if second is not None:
        if value.kind is DateKind.BETWEEN:
            text = f"between {_date_en(first)} and {_date_en(second)}"
        else:
            text = f"from {_date_en(first)} to {_date_en(second)}"
    elif value.kind in _PREFIX_EN:
        text = f"{_PREFIX_EN[value.kind]} {_date_en(first)}"
    else:
        text = _date_en(first)
    if include_phrase and value.phrase:
        text = f'{text} ("{value.phrase}")'
    return text
