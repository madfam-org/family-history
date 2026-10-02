"""Living-status inference, the basis of «living people are private by default».

The rule (docs/PRIVACY.md §1):

1. `DECEASED` only with an evidenced death, burial or cremation event.
2. Otherwise, with a birth bound: `LIVING` when the person may have been born within the last
   `window_years` (110 by default) of `today`; `PRESUMED_DECEASED` when every possible birth
   date is older than that.
3. Otherwise `UNKNOWN`.

The birth bound is the latest possible birth day: from the birth event, or from a baptism or
christening (birth is never after them). Approximate dates use their widened bounds, which
errs on the side of privacy. Calendars without day bounds (French Republican, Hebrew) are
ignored for this purpose. All functions are pure: `today` is always passed in.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .dates import (
    DEFAULT_APPROX_YEARS,
    DateValue,
    UnsupportedCalendarError,
    date_from_jdn,
    jdn_from_date,
)
from .events import EventType

__all__ = [
    "DEFAULT_LIVING_WINDOW_YEARS",
    "LivingAssessment",
    "LivingBasis",
    "LivingStatus",
    "VitalEvent",
    "assess_living",
    "infer_living_status",
    "is_private_by_default",
]

DEFAULT_LIVING_WINDOW_YEARS = 110


class LivingStatus(StrEnum):
    """Whether a person is treated as living."""

    LIVING = "living"
    DECEASED = "deceased"
    PRESUMED_DECEASED = "presumed_deceased"
    UNKNOWN = "unknown"

    @property
    def contract_value(self) -> str:
        """The v1 API value (`living|deceased|unknown`); a presumption maps to `deceased`.

        Visibility must still come from `is_private_by_default`, never from this value.
        """
        return "deceased" if self is LivingStatus.PRESUMED_DECEASED else self.value

    @property
    def label_es(self) -> str:
        return _LABELS[self][0]

    @property
    def label_en(self) -> str:
        return _LABELS[self][1]


_LABELS: dict[LivingStatus, tuple[str, str]] = {
    LivingStatus.LIVING: ("Con vida", "Living"),
    LivingStatus.DECEASED: ("Finado/a", "Deceased"),
    LivingStatus.PRESUMED_DECEASED: ("Probablemente finado/a", "Presumed deceased"),
    LivingStatus.UNKNOWN: ("Sin datos suficientes", "Unknown"),
}


class LivingBasis(StrEnum):
    """Why a status was inferred."""

    DEATH_EVIDENCE = "death_evidence"
    BORN_WITHIN_WINDOW = "born_within_window"
    BORN_BEFORE_WINDOW = "born_before_window"
    NO_BIRTH_BOUND = "no_birth_bound"


@dataclass(frozen=True, slots=True)
class VitalEvent:
    """An event as the living rule sees it. `has_evidence` means a cited source backs it."""

    event_type: EventType
    date: DateValue | None = None
    has_evidence: bool = False


@dataclass(frozen=True, slots=True)
class LivingAssessment:
    """The inferred status, its basis and the latest possible birth day (if known)."""

    status: LivingStatus
    basis: LivingBasis
    latest_birth: dt.date | None

    @property
    def private_by_default(self) -> bool:
        return is_private_by_default(self.status)


def _cutoff(today: dt.date, years: int) -> dt.date:
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February in a common year
        return today.replace(year=today.year - years, day=28)


def assess_living(
    events: Iterable[VitalEvent],
    *,
    today: dt.date,
    window_years: int = DEFAULT_LIVING_WINDOW_YEARS,
    approx_years: int = DEFAULT_APPROX_YEARS,
) -> LivingAssessment:
    """Apply the living rule to a person's events (see the module docstring)."""
    if window_years < 1:
        raise ValueError("window_years must be at least 1")
    latest_jdn: int | None = None
    earliest_jdn: int | None = None
    deceased = False
    for event in events:
        if event.event_type.is_death_evidence and event.has_evidence:
            deceased = True
        if not event.event_type.bounds_birth or event.date is None:
            continue
        try:
            lo, hi = event.date.jdn_bounds(approx_years)
        except UnsupportedCalendarError:
            continue
        if hi is not None:
            latest_jdn = hi if latest_jdn is None else min(latest_jdn, hi)
        if lo is not None and event.event_type is EventType.BIRTH:
            earliest_jdn = lo if earliest_jdn is None else max(earliest_jdn, lo)
    latest_birth = _safe_date(latest_jdn)
    if deceased:
        return LivingAssessment(LivingStatus.DECEASED, LivingBasis.DEATH_EVIDENCE, latest_birth)
    cutoff = jdn_from_date(_cutoff(today, window_years))
    if latest_jdn is not None:
        if latest_jdn >= cutoff:
            return LivingAssessment(
                LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW, latest_birth
            )
        return LivingAssessment(
            LivingStatus.PRESUMED_DECEASED, LivingBasis.BORN_BEFORE_WINDOW, latest_birth
        )
    if earliest_jdn is not None and earliest_jdn >= cutoff:
        return LivingAssessment(LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW, None)
    return LivingAssessment(LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND, None)


def _safe_date(jdn: int | None) -> dt.date | None:
    if jdn is None:
        return None
    try:
        return date_from_jdn(jdn)
    except (ValueError, OverflowError):
        return None


def infer_living_status(
    events: Iterable[VitalEvent],
    *,
    today: dt.date,
    window_years: int = DEFAULT_LIVING_WINDOW_YEARS,
    approx_years: int = DEFAULT_APPROX_YEARS,
) -> LivingStatus:
    """Return just the status of `assess_living`."""
    return assess_living(
        events, today=today, window_years=window_years, approx_years=approx_years
    ).status


def is_private_by_default(status: LivingStatus) -> bool:
    """True for `LIVING` and `UNKNOWN`: nothing about them is ever public."""
    return status in (LivingStatus.LIVING, LivingStatus.UNKNOWN)
