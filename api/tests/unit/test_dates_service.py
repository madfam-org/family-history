"""Event dates through the domain library: canonical values, typed text, bounds, display."""

from __future__ import annotations

from datetime import date

import pytest

from family_history.errors import APIError
from family_history.services import dates


def test_date_value_is_canonicalized_with_bounds() -> None:
    parsed = dates.event_date("abt  1890", None)
    assert parsed == dates.EventDate("ABT 1890", None, date(1885, 1, 1), date(1895, 12, 31))


def test_date_original_is_read_as_spanish_and_kept() -> None:
    parsed = dates.event_date(None, "15 de marzo de 1923")
    assert parsed.value == "15 MAR 1923"
    assert parsed.original == "15 de marzo de 1923"
    assert parsed.earliest == parsed.latest == date(1923, 3, 15)
    # All-numeric dates are day/month/year (es-MX).
    assert dates.event_date(None, "03/04/1990").value == "3 APR 1990"


def test_date_original_falls_back_to_gedcom_syntax() -> None:
    parsed = dates.event_date(None, "BET 1890 AND 1895")
    assert parsed.value == "BET 1890 AND 1895"
    assert parsed.original == "BET 1890 AND 1895"


@pytest.mark.parametrize(
    ("value", "original", "code"),
    [
        (None, "1890-1895", "ambiguous_date"),
        (None, "algún día", "invalid_date"),
        ("hacia 1890", None, "invalid_date"),
        ("@#DJULIAN@ 1700", None, "invalid_date"),
        ("BET 1900 AND 1850", None, "invalid_date"),
    ],
)
def test_unreadable_dates_are_422(value: str | None, original: str | None, code: str) -> None:
    with pytest.raises(APIError) as caught:
        dates.event_date(value, original)
    assert caught.value.status_code == 422
    assert caught.value.code == code


def test_open_and_calendar_bounds() -> None:
    assert dates.event_date("FROM 1900", None).latest is None
    julian = dates.event_date("JULIAN 1700", None)
    assert julian.earliest == date(1700, 1, 11)
    french = dates.event_date("FRENCH_R 3 VEND 12", None)
    assert french.value is not None and (french.earliest, french.latest) == (None, None)


def test_display_in_both_languages() -> None:
    shown = dates.display("ABT 1891")
    assert shown == dates.Display(es="hacia 1891", en="about 1891")
    assert dates.display(None) is None
    assert dates.display("not a date") is None
    assert dates.event_date(None, None) == dates.EventDate.empty()
