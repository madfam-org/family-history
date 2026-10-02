"""Tests for the forgiving Spanish date input parser."""

from __future__ import annotations

import pytest

from family_history.domain.dates import DateKind, DateParseError, parse_user_date_es


@pytest.mark.parametrize(
    ("typed", "gedcom"),
    [
        ("15 de marzo de 1923", "15 MAR 1923"),
        ("15 de Marzo del 1923", "15 MAR 1923"),
        ("15/03/1923", "15 MAR 1923"),
        ("15-03-1923", "15 MAR 1923"),
        ("15.03.1923", "15 MAR 1923"),
        ("1923-03-15", "15 MAR 1923"),
        ("15-mar-1923", "15 MAR 1923"),
        ("15 mar. 1923", "15 MAR 1923"),
        ("March 15, 1923", "15 MAR 1923"),
        ("1o. de enero de 1900", "1 JAN 1900"),
        ("1º de enero de 1900", "1 JAN 1900"),
        ("1ro. de enero de 1900", "1 JAN 1900"),
        ("primero de enero de 1900", "1 JAN 1900"),
        ("marzo 1923", "MAR 1923"),
        ("marzo de 1923", "MAR 1923"),
        ("sept. 1923", "SEP 1923"),
        ("setiembre de 1923", "SEP 1923"),
        ("03/1923", "MAR 1923"),
        ("1923", "1923"),
        ("c. 1890", "ABT 1890"),
        ("c.1890", "ABT 1890"),
        ("ca. 1890", "ABT 1890"),
        ("ca 1890", "ABT 1890"),
        ("circa 1890", "ABT 1890"),
        ("1890?", "ABT 1890"),
        ("1890 ?", "ABT 1890"),
        ("hacia 1890", "ABT 1890"),
        ("hacia el 15 de marzo de 1890", "ABT 15 MAR 1890"),
        ("aprox. 1890", "ABT 1890"),
        ("aproximadamente 1890", "ABT 1890"),
        ("alrededor de 1890", "ABT 1890"),
        ("cerca de 1890", "ABT 1890"),
        ("calculado 1885", "CAL 1885"),
        ("calc. 1885", "CAL 1885"),
        ("estimado 1885", "EST 1885"),
        ("est. 1885", "EST 1885"),
        ("antes de 1900", "BEF 1900"),
        ("antes del 15 de marzo de 1900", "BEF 15 MAR 1900"),
        ("después de 1880", "AFT 1880"),
        ("despues de 1880", "AFT 1880"),
        ("entre 1890 y 1895", "BET 1890 AND 1895"),
        ("entre el 1 de enero de 1890 y el 5 de mayo de 1895", "BET 1 JAN 1890 AND 5 MAY 1895"),
        ("de 1910 a 1920", "FROM 1910 TO 1920"),
        ("del 15 de marzo de 1910 al 2 de abril de 1920", "FROM 15 MAR 1910 TO 2 APR 1920"),
        ("desde 1910 hasta 1920", "FROM 1910 TO 1920"),
        ("desde 1910", "FROM 1910"),
        ("a partir de 1910", "FROM 1910"),
        ("hasta 1920", "TO 1920"),
        ("década de 1890", "BET 1890 AND 1899"),
        ("1890s", "BET 1890 AND 1899"),
        ("los años 1890", "BET 1890 AND 1899"),
        ("44 a. C.", "44 BCE"),
        ("44 a.C.", "44 BCE"),
        ("44 antes de Cristo", "44 BCE"),
        ("1523 d. C.", "1523"),
        ("15 de marzo de 1580 (juliano)", "JULIAN 15 MAR 1580"),
        ("15 de marzo de 1580, calendario juliano", "JULIAN 15 MAR 1580"),
        ("lunes 15 de marzo de 1926", "15 MAR 1926"),
        ("Lunes, 15 de marzo de 1926", "15 MAR 1926"),
        ("  15   de  MARZO  de 1923  ", "15 MAR 1923"),
    ],
)
def test_accepts_what_people_type(typed: str, gedcom: str) -> None:
    value = parse_user_date_es(typed)
    assert value.format() == gedcom
    assert value.original == typed


@pytest.mark.parametrize(
    ("typed", "fragment"),
    [
        ("1890-1895", "ambiguous"),
        ("1890 – 1895", "ambiguous"),
        ("03/15/1923", "day/month/year"),
        ("15/03/23", "which century"),
        ("15 de marzo de 23", "which century"),
        ("23", "which century"),
    ],
)
def test_ambiguous_input_is_rejected_with_code(typed: str, fragment: str) -> None:
    with pytest.raises(DateParseError) as info:
        parse_user_date_es(typed)
    assert fragment in str(info.value)
    assert info.value.code == "ambiguous_date"


@pytest.mark.parametrize(
    ("typed", "fragment"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("algún día", "unrecognized"),
        ("lunes 15 de marzo de 1923", "jueves"),
        ("lunes 1923", "full date"),
        ("lunes", "missing"),
        ("hacia 1890?", "not both"),
        ("18?90", "only understood at the end"),
        ("entre 1890", "entre <fecha> y <fecha>"),
        ("entre 1895 y 1890", "after the AND date"),
        ("de 1920 a 1910", "after the TO date"),
        ("de 1910 a 1915 a 1920", "de <fecha> a <fecha>"),
        ("31 de febrero de 1923", "out of range"),
        ("15/13/1923", "month 13"),
        ("1923-13-01", "month 13"),
        ("00/1923", "month 0"),
        ("década de 1895", "does not start a decade"),
        ("marzo marzo 1923", "write a date like"),
        ("15 de marzo de 19234", "too many digits"),
        ("0", "which century"),
    ],
)
def test_invalid_input_is_rejected(typed: str, fragment: str) -> None:
    with pytest.raises(DateParseError, match=fragment):
        parse_user_date_es(typed)


def test_short_bce_years_are_allowed() -> None:
    assert parse_user_date_es("44 a. C.").kind is DateKind.DATE
    assert parse_user_date_es("de 500 a. C. a 400 a. C.").format() == "FROM 500 BCE TO 400 BCE"


def test_weekday_requires_gregorian_ce() -> None:
    with pytest.raises(DateParseError, match="Gregorian"):
        parse_user_date_es("lunes 15 de marzo de 1580 (juliano)")
