"""Privacy rules from docs/PRIVACY.md that the API enforces on every read.

- Living status follows `family_history.domain.living`: `deceased` only with a death, burial or
  cremation event; otherwise, with a birth bound, `living` when born within the last 110 years
  and `presumed_deceased` when every possible birth is older; otherwise `unknown`. Birth bounds
  come from `event.date_latest`, which the domain library fills at integration; until then
  people without a death event are `unknown`.
- `living` and `unknown` people are private by default (treated as living).
- `private` people are visible only to their creator.
- Sensitive facts (events or assertions with a sensitivity class) about people treated as living
  are visible only to whoever recorded them, until consent flows exist.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, and_, or_

from family_history.models import Person
from family_history.models.enums import EventType, LivingStatus, Sensitivity, Visibility

LIVING_HORIZON_YEARS = 110

DEATH_EVENT_TYPES = frozenset({EventType.DEATH, EventType.BURIAL, EventType.CREMATION})
BIRTH_BOUND_EVENT_TYPES = frozenset({EventType.BIRTH, EventType.BAPTISM, EventType.CHRISTENING})
SACRAMENT_EVENT_TYPES = frozenset(
    {
        EventType.BAPTISM,
        EventType.CHRISTENING,
        EventType.CONFIRMATION,
        EventType.FIRST_COMMUNION,
        EventType.RELIGIOUS_MARRIAGE,
    }
)
# Fact kinds that are recorded as assertion fields (domain.sensitivity.FactKind).
FIELD_SENSITIVITY: dict[str, Sensitivity] = {
    "cause_of_death": Sensitivity.HEALTH,
    "medical_note": Sensitivity.HEALTH,
    "religious_affiliation": Sensitivity.RELIGION,
    "ethnic_origin": Sensitivity.ETHNICITY,
    "political_affiliation": Sensitivity.POLITICAL,
}


def default_sensitivity(event_type: str) -> Sensitivity | None:
    """Sacraments (including religious marriage) default to `religion`."""
    return Sensitivity.RELIGION if event_type in SACRAMENT_EVENT_TYPES else None


def default_field_sensitivity(field: str) -> Sensitivity | None:
    return FIELD_SENSITIVITY.get(field)


@dataclass(frozen=True)
class LifeEvent:
    type: str
    date_latest: date | None


def _years_before(today: date, years: int) -> date:
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # 29 February
        return today.replace(year=today.year - years, day=28)


def compute_living_status(events: Iterable[LifeEvent], today: date) -> LivingStatus:
    """Derive the living status from the events where the person is the principal."""
    births: list[date] = []
    for event in events:
        if event.type in DEATH_EVENT_TYPES:
            return LivingStatus.DECEASED
        if event.type in BIRTH_BOUND_EVENT_TYPES and event.date_latest is not None:
            births.append(event.date_latest)
    if not births:
        return LivingStatus.UNKNOWN
    if max(births) < _years_before(today, LIVING_HORIZON_YEARS):
        return LivingStatus.PRESUMED_DECEASED
    return LivingStatus.LIVING


def treated_as_living(living_status: str) -> bool:
    """Private by default: everyone not deceased or presumed deceased."""
    return living_status in (LivingStatus.LIVING.value, LivingStatus.UNKNOWN.value)


def visible_people(viewer_sub: str) -> ColumnElement[bool]:
    """SQL filter: not soft-deleted, and not someone else's private person."""
    return and_(
        Person.deleted_at.is_(None),
        or_(Person.visibility != Visibility.PRIVATE.value, Person.created_by == viewer_sub),
    )


def sensitive_visible(
    sensitivity: str | None, author_sub: str, viewer_sub: str, about_living: bool
) -> bool:
    if sensitivity is None or not about_living:
        return True
    return author_sub == viewer_sub
