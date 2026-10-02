"""Unit tests for the GEDCOM 7 DateValue grammar, bounds and display."""

from __future__ import annotations

import datetime as dt

import pytest

from family_history.domain.dates import (
    Calendar,
    CalendarDate,
    DateBoundsError,
    DateKind,
    DateParseError,
    DateValue,
    UnsupportedCalendarError,
    canonicalize_date_value,
    date_from_jdn,
    format_date_value,
    humanize_en,
    humanize_es,
    jdn_from_date,
    parse_calendar_date,
    parse_date_value,
)


@pytest.mark.parametrize(
    ("text", "kind", "canonical"),
    [
        ("", DateKind.EMPTY, ""),
        ("1923", DateKind.DATE, "1923"),
        ("MAR 1923", DateKind.DATE, "MAR 1923"),
        ("15 MAR 1923", DateKind.DATE, "15 MAR 1923"),
        ("ABT 1891", DateKind.ABOUT, "ABT 1891"),
        ("CAL 1885", DateKind.CALCULATED, "CAL 1885"),
        ("EST 1885", DateKind.ESTIMATED, "EST 1885"),
        ("BEF 1900", DateKind.BEFORE, "BEF 1900"),
        ("AFT 1880", DateKind.AFTER, "AFT 1880"),
        ("BET 1890 AND 1895", DateKind.BETWEEN, "BET 1890 AND 1895"),
        ("FROM 1910", DateKind.FROM, "FROM 1910"),
        ("TO 1920", DateKind.TO, "TO 1920"),
        ("FROM 1910 TO 1920", DateKind.FROM_TO, "FROM 1910 TO 1920"),
        ("JULIAN 11 FEB 1732", DateKind.DATE, "JULIAN 11 FEB 1732"),
        ("GREGORIAN 15 MAR 1923", DateKind.DATE, "15 MAR 1923"),
        ("44 BCE", DateKind.DATE, "44 BCE"),
        ("JULIAN 15 MAR 44 BCE", DateKind.DATE, "JULIAN 15 MAR 44 BCE"),
        ("FRENCH_R 1 VEND 2", DateKind.DATE, "FRENCH_R 1 VEND 2"),
        ("FRENCH_R 6 COMP 3", DateKind.DATE, "FRENCH_R 6 COMP 3"),
        ("HEBREW 1 TSH 5784", DateKind.DATE, "HEBREW 1 TSH 5784"),
        ("  abt   05  mar 1891 ", DateKind.ABOUT, "ABT 5 MAR 1891"),
        ("bet julian 1700 and 1705", DateKind.BETWEEN, "BET JULIAN 1700 AND 1705"),
        ("from 0900 to 0950", DateKind.FROM_TO, "FROM 900 TO 950"),
    ],
)
def test_parse_and_canonical_form(text: str, kind: DateKind, canonical: str) -> None:
    value = parse_date_value(text)
    assert value.kind is kind
    assert format_date_value(value) == canonical
    assert value.format() == canonical
    assert canonicalize_date_value(text) == canonical
    assert value.original == text


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("1750/51", "dual year"),
        ("@#DJULIAN@ 1700", "@#DJULIAN@"),
        ("INT 1900 (about then)", "PHRASE"),
        ("(about then)", "PHRASE"),
        ("ABOUT 1900", "ABT"),
        ("BEFORE 1900", "BEF"),
        ("AFTER 1900", "AFT"),
        ("BETWEEN 1900 AND 1910", "BET"),
        ("100 BC", "BCE"),
        ("100 B.C.", "BCE"),
        ("ABT", "missing after ABT"),
        ("BET 1900", "exactly one AND"),
        ("BET 1900 AND", "missing after AND"),
        ("AND 1900", "AND is only valid"),
        ("FROM 1900 TO 1910 TO 1920", "exactly one TO"),
        ("BET 1895 AND 1890", "after the AND date"),
        ("FROM 1920 TO 1910", "after the TO date"),
        ("31 FEB 1900", "out of range"),
        ("29 FEB 1900", "out of range"),
        ("0 JAN 1900", "out of range"),
        ("0", "year 0"),
        ("15 MARCH 1923", "not a GREGORIAN month"),
        ("1 VEND 1923", "not a GREGORIAN month"),
        ("FRENCH_R 1 JAN 2", "not a FRENCH_R month"),
        ("HEBREW 1 TSH 5784 BCE", "no BCE"),
        ("_MYCAL 1900", "extension calendar"),
        ("1900 _EPOCH", "extension epoch"),
        ("1 2 3 4 1900", "unexpected words"),
        ("JULIAN", "needs a year"),
        ("19x0", "must be digits"),
        ("١٩٢٣", "must be digits"),
    ],
)
def test_parse_errors_are_helpful(text: str, fragment: str) -> None:
    with pytest.raises(DateParseError) as info:
        parse_date_value(text)
    assert fragment in str(info.value)
    assert info.value.text == text
    assert info.value.code == "invalid_date"


def test_julian_leap_day_is_valid_in_1900() -> None:
    value = parse_date_value("JULIAN 29 FEB 1900")
    assert value.earliest == dt.date(1900, 3, 13)


def test_phrase_is_kept_and_blank_phrase_dropped() -> None:
    value = parse_date_value("", phrase="durante la Revolución")
    assert value.is_empty
    assert value.phrase == "durante la Revolución"
    assert humanize_es(value) == "durante la Revolución"
    assert parse_date_value("1923", phrase="   ").phrase is None
    with pytest.raises(ValueError, match="blank"):
        DateValue(DateKind.EMPTY, phrase=" ")


def test_original_is_not_part_of_equality() -> None:
    assert parse_date_value("abt 1891") == parse_date_value("ABT 1891")
    built = DateValue(DateKind.ABOUT, CalendarDate(1891))
    assert built.original == "ABT 1891"


def test_date_value_shape_is_validated() -> None:
    with pytest.raises(ValueError, match="exactly 2"):
        DateValue(DateKind.BETWEEN, CalendarDate(1900))
    with pytest.raises(ValueError, match="exactly 0"):
        DateValue(DateKind.EMPTY, CalendarDate(1900))
    with pytest.raises(ValueError, match="needs a month"):
        CalendarDate(1900, day=3)


def test_parse_calendar_date() -> None:
    value = parse_calendar_date("JULIAN 11 FEB 1732")
    assert value == CalendarDate(1732, "FEB", 11, Calendar.JULIAN)
    assert value.precision == "day"
    assert CalendarDate(1732, "FEB").precision == "month"
    assert CalendarDate(1732).precision == "year"


# Well-known Julian (Old Style) to Gregorian (New Style) conversions.
@pytest.mark.parametrize(
    ("julian", "gregorian"),
    [
        ("JULIAN 4 OCT 1582", dt.date(1582, 10, 14)),
        ("JULIAN 5 OCT 1582", dt.date(1582, 10, 15)),
        ("JULIAN 23 APR 1616", dt.date(1616, 5, 3)),  # Shakespeare's death
        ("JULIAN 25 DEC 1642", dt.date(1643, 1, 4)),  # Newton's birth
        ("JULIAN 11 FEB 1732", dt.date(1732, 2, 22)),  # Washington's birth
        ("JULIAN 2 SEP 1752", dt.date(1752, 9, 13)),  # last Old Style day in Britain
        ("JULIAN 29 FEB 1700", dt.date(1700, 3, 11)),
        ("JULIAN 1 FEB 1918", dt.date(1918, 2, 14)),  # Russia's switch
        ("JULIAN 1 JAN 1900", dt.date(1900, 1, 13)),
        ("JULIAN 1 MAR 2100", dt.date(2100, 3, 15)),
    ],
)
def test_julian_converts_to_gregorian(julian: str, gregorian: dt.date) -> None:
    value = parse_date_value(julian)
    assert value.earliest == gregorian
    assert value.latest == gregorian


def test_julian_day_numbers_of_reference_epochs() -> None:
    assert parse_date_value("JULIAN 1 JAN 4713 BCE").jdn_bounds() == (0, 0)
    assert parse_date_value("1 JAN 2000").jdn_bounds() == (2451545, 2451545)
    assert jdn_from_date(dt.date(2000, 1, 1)) == 2451545
    assert date_from_jdn(2451545) == dt.date(2000, 1, 1)


@pytest.mark.parametrize(
    ("text", "earliest", "latest"),
    [
        ("", None, None),
        ("1923", dt.date(1923, 1, 1), dt.date(1923, 12, 31)),
        ("FEB 1924", dt.date(1924, 2, 1), dt.date(1924, 2, 29)),
        ("FEB 1923", dt.date(1923, 2, 1), dt.date(1923, 2, 28)),
        ("15 MAR 1923", dt.date(1923, 3, 15), dt.date(1923, 3, 15)),
        ("ABT 1891", dt.date(1886, 1, 1), dt.date(1896, 12, 31)),
        ("CAL MAR 1891", dt.date(1886, 3, 1), dt.date(1896, 3, 31)),
        ("EST 29 FEB 1904", dt.date(1899, 2, 28), dt.date(1909, 2, 28)),
        ("BEF 1900", None, dt.date(1900, 12, 31)),
        ("AFT 1880", dt.date(1880, 1, 1), None),
        ("BET 1890 AND 1895", dt.date(1890, 1, 1), dt.date(1895, 12, 31)),
        ("FROM 1910", dt.date(1910, 1, 1), None),
        ("TO 1920", None, dt.date(1920, 12, 31)),
        ("FROM 1910 TO MAR 1920", dt.date(1910, 1, 1), dt.date(1920, 3, 31)),
        ("BET JULIAN 1700 AND 1705", dt.date(1700, 1, 11), dt.date(1705, 12, 31)),
    ],
)
def test_bounds(text: str, earliest: dt.date | None, latest: dt.date | None) -> None:
    value = parse_date_value(text)
    assert value.earliest == earliest
    assert value.latest == latest


def test_approximation_margin_is_configurable() -> None:
    bounds = parse_date_value("ABT 1891").bounds(approx_years=0)
    assert (bounds.earliest, bounds.latest) == (dt.date(1891, 1, 1), dt.date(1891, 12, 31))
    with pytest.raises(ValueError, match="negative"):
        parse_date_value("ABT 1891").jdn_bounds(approx_years=-1)


def test_unsupported_calendars_parse_but_have_no_bounds() -> None:
    for text in ("FRENCH_R 1 VEND 2", "HEBREW 1 TSH 5784"):
        value = parse_date_value(text)
        with pytest.raises(UnsupportedCalendarError, match="round-trips"):
            _ = value.earliest
    # Mixed-calendar ranges skip the order check rather than guess.
    assert parse_date_value("BET HEBREW 5784 AND 1700").kind is DateKind.BETWEEN


def test_bce_bounds_use_jdn() -> None:
    value = parse_date_value("44 BCE")
    with pytest.raises(DateBoundsError, match="jdn_bounds"):
        _ = value.earliest
    lo, hi = value.jdn_bounds()
    assert lo is not None and hi is not None and lo < hi < 1721426


@pytest.mark.parametrize(
    ("text", "es", "en"),
    [
        ("15 MAR 1923", "15 de marzo de 1923", "15 March 1923"),
        ("MAR 1923", "marzo de 1923", "March 1923"),
        ("ABT 1891", "hacia 1891", "about 1891"),
        ("ABT 15 MAR 1891", "hacia el 15 de marzo de 1891", "about 15 March 1891"),
        ("CAL 1885", "calculado 1885", "calculated 1885"),
        ("EST 1885", "estimado 1885", "estimated 1885"),
        ("BEF 1900", "antes de 1900", "before 1900"),
        ("BEF 15 MAR 1900", "antes del 15 de marzo de 1900", "before 15 March 1900"),
        ("AFT 1880", "después de 1880", "after 1880"),
        ("AFT 2 JAN 1880", "después del 2 de enero de 1880", "after 2 January 1880"),
        ("BET 1890 AND 1895", "entre 1890 y 1895", "between 1890 and 1895"),
        (
            "BET 1 JAN 1890 AND 5 MAY 1895",
            "entre el 1 de enero de 1890 y el 5 de mayo de 1895",
            "between 1 January 1890 and 5 May 1895",
        ),
        ("FROM 1910 TO 1920", "de 1910 a 1920", "from 1910 to 1920"),
        (
            "FROM 15 MAR 1910 TO 2 APR 1920",
            "del 15 de marzo de 1910 al 2 de abril de 1920",
            "from 15 March 1910 to 2 April 1920",
        ),
        ("FROM 1910", "desde 1910", "from 1910"),
        ("TO 1920", "hasta 1920", "until 1920"),
        ("44 BCE", "44 a. C.", "44 BCE"),
        (
            "JULIAN 11 FEB 1732",
            "11 de febrero de 1732 (calendario juliano)",
            "11 February 1732 (Julian calendar)",
        ),
        (
            "FRENCH_R 1 VEND 2",
            "1 de vendimiario de 2 (calendario republicano francés)",
            "1 Vendémiaire 2 (French Republican calendar)",
        ),
        (
            "HEBREW ADS 5784",
            "adar II de 5784 (calendario hebreo)",
            "Adar II 5784 (Hebrew calendar)",
        ),
        ("", "fecha desconocida", "unknown date"),
    ],
)
def test_humanize(text: str, es: str, en: str) -> None:
    value = parse_date_value(text)
    assert humanize_es(value) == es
    assert humanize_en(value) == en


def test_humanize_with_phrase() -> None:
    value = parse_date_value("ABT 1910", phrase="cuando empezó la Revolución")
    assert humanize_es(value) == "hacia 1910"
    assert humanize_es(value, include_phrase=True) == "hacia 1910 («cuando empezó la Revolución»)"
    assert humanize_en(value, include_phrase=True) == 'about 1910 ("cuando empezó la Revolución")'
    assert humanize_en(parse_date_value("", phrase="unknown")) == "unknown"


def test_kind_helpers() -> None:
    assert DateKind.ABOUT.is_approximate and not DateKind.ABOUT.is_range
    assert DateKind.BETWEEN.is_range and DateKind.BETWEEN.date_count == 2
    assert DateKind.FROM_TO.is_period and DateKind.TO.is_period
    assert DateKind.EMPTY.date_count == 0 and DateKind.DATE.date_count == 1
