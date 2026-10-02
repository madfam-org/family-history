"""Property tests: date round trips, canonical idempotence, bounds and calendar arithmetic."""

from __future__ import annotations

import datetime as dt

from hypothesis import given, settings
from hypothesis import strategies as st

from family_history.domain.dates import (
    Calendar,
    CalendarDate,
    DateKind,
    DateValue,
    canonicalize_date_value,
    date_from_jdn,
    format_date_value,
    humanize_en,
    humanize_es,
    jdn_from_date,
    parse_date_value,
    parse_user_date_es,
)
from family_history.domain.dates._calendars import (
    days_in_month,
    gregorian_to_jdn,
    julian_to_jdn,
    months_for,
)

_SUPPORTED = (Calendar.GREGORIAN, Calendar.JULIAN)


@st.composite
def calendar_dates(
    draw: st.DrawFn,
    calendars: tuple[Calendar, ...] = tuple(Calendar),
    min_year: int = 1,
    allow_bce: bool = True,
) -> CalendarDate:
    calendar = draw(st.sampled_from(calendars))
    bce = allow_bce and calendar in _SUPPORTED and draw(st.booleans())
    year = draw(st.integers(min_value=min_year, max_value=4000 if bce else 9998))
    precision = draw(st.sampled_from(("year", "month", "day")))
    if precision == "year":
        return CalendarDate(year, calendar=calendar, bce=bce)
    months = months_for(calendar)
    month_index = draw(st.integers(min_value=1, max_value=len(months)))
    month = months[month_index - 1]
    if precision == "month":
        return CalendarDate(year, month, calendar=calendar, bce=bce)
    astro = 1 - year if bce else year
    day = draw(st.integers(min_value=1, max_value=days_in_month(calendar, astro, month_index)))
    return CalendarDate(year, month, day, calendar, bce)


def _ordered(first: CalendarDate, second: CalendarDate) -> tuple[CalendarDate, CalendarDate]:
    if first.calendar in _SUPPORTED and second.calendar in _SUPPORTED:
        if first.jdn_bounds()[0] > second.jdn_bounds()[0]:
            return second, first
    return first, second


@st.composite
def date_values(
    draw: st.DrawFn,
    calendars: tuple[Calendar, ...] = tuple(Calendar),
    min_year: int = 1,
    allow_bce: bool = True,
    kinds: tuple[DateKind, ...] = tuple(DateKind),
) -> DateValue:
    kind = draw(st.sampled_from(kinds))
    dates = calendar_dates(calendars, min_year, allow_bce)
    if kind.date_count == 0:
        return DateValue(kind)
    first = draw(dates)
    if kind.date_count == 1:
        return DateValue(kind, first)
    start, end = _ordered(first, draw(dates))
    return DateValue(kind, start, end)


@given(date_values())
def test_format_then_parse_round_trips(value: DateValue) -> None:
    text = format_date_value(value)
    assert parse_date_value(text) == value
    assert canonicalize_date_value(text) == text


def _messy(text: str, data: st.DataObject) -> str:
    words = []
    for word in text.split():
        if word.isdigit() and data.draw(st.booleans()):
            word = "0" * data.draw(st.integers(1, 2)) + word
        if data.draw(st.booleans()):
            word = word.lower()
        words.append(word)
    spaces = data.draw(st.lists(st.sampled_from([" ", "  ", "\t"]), min_size=len(words) + 1,
                                max_size=len(words) + 1))  # fmt: skip
    return spaces[0] + "".join(w + s for w, s in zip(words, spaces[1:], strict=True))


@given(date_values(), st.data())
def test_canonical_form_ignores_case_spacing_and_zeros(
    value: DateValue, data: st.DataObject
) -> None:
    canonical = format_date_value(value)
    messy = _messy(canonical, data)
    assert canonicalize_date_value(messy) == canonical
    assert canonicalize_date_value(canonicalize_date_value(messy)) == canonical


@given(date_values(calendars=_SUPPORTED))
def test_bounds_are_ordered_and_cover_the_date(value: DateValue) -> None:
    lo, hi = value.jdn_bounds()
    if lo is not None and hi is not None:
        assert lo <= hi
    if value.first is not None and value.kind.date_count == 1:
        first_lo, first_hi = value.first.jdn_bounds()
        assert lo is None or lo <= first_lo
        assert hi is None or hi >= first_hi


@given(date_values(calendars=_SUPPORTED, min_year=10, allow_bce=False), st.integers(0, 10))
def test_wider_margin_never_narrows(value: DateValue, years: int) -> None:
    lo, hi = value.jdn_bounds(approx_years=years)
    wider_lo, wider_hi = value.jdn_bounds(approx_years=years + 1)
    if lo is not None and wider_lo is not None:
        assert wider_lo <= lo
    if hi is not None and wider_hi is not None:
        assert wider_hi >= hi


@given(st.dates())
def test_gregorian_jdn_matches_datetime(day: dt.date) -> None:
    jdn = gregorian_to_jdn(day.year, day.month, day.day)
    assert jdn == jdn_from_date(day)
    assert date_from_jdn(jdn) == day


@given(st.dates(min_value=dt.date(1900, 3, 14), max_value=dt.date(2100, 2, 27)))
def test_julian_lags_gregorian_by_13_days_in_1900_to_2100(day: dt.date) -> None:
    julian = day - dt.timedelta(days=13)
    assert julian_to_jdn(julian.year, julian.month, julian.day) == jdn_from_date(day)


@given(st.dates(min_value=dt.date(1583, 1, 1), max_value=dt.date(1699, 12, 31)))
def test_julian_lags_gregorian_by_10_days_in_1583_to_1699(day: dt.date) -> None:
    julian = day - dt.timedelta(days=10)
    assert julian_to_jdn(julian.year, julian.month, julian.day) == jdn_from_date(day)


@given(date_values())
def test_humanizers_never_return_blank(value: DateValue) -> None:
    assert humanize_es(value).strip()
    assert humanize_en(value).strip()


_USER_KINDS = tuple(kind for kind in DateKind if kind is not DateKind.EMPTY)


@settings(max_examples=300)
@given(date_values(calendars=_SUPPORTED, min_year=100, allow_bce=True, kinds=_USER_KINDS))
def test_spanish_display_text_parses_back(value: DateValue) -> None:
    """What the UI shows in Spanish is something a family can type back in."""
    assert parse_user_date_es(humanize_es(value)) == value
