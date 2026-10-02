"""Privacy rules from docs/PRIVACY.md that the API enforces on every read.

- A person is treated as living unless proven dead (a death or burial event). People born more
  than 110 years ago with no death event are `unknown`, not `living`. Birth bounds come from
  `event.date_latest`, which the domain library fills; until it does, everyone without a death
  event is `living`, which is the conservative reading.
- `private` people are visible only to their creator.
- Sensitive facts (events or assertions with a sensitivity class) about living people are
  visible only to whoever recorded them, until consent flows exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, and_, or_

from family_history.models import Person
from family_history.models.enums import LivingStatus, Sensitivity, Visibility

LIVING_HORIZON_YEARS = 110

DEATH_EVENT_TYPES = frozenset({"death", "burial", "cremation"})
BIRTH_EVENT_TYPES = frozenset({"birth", "baptism"})
SACRAMENT_EVENT_TYPES = frozenset(
    {"baptism", "confirmation", "first_communion", "religious_marriage"}
)
HEALTH_EVENT_TYPES = frozenset({"medical", "illness", "cause_of_death"})


def default_sensitivity(event_type: str) -> Sensitivity | None:
    if event_type in SACRAMENT_EVENT_TYPES:
        return Sensitivity.RELIGION
    if event_type in HEALTH_EVENT_TYPES:
        return Sensitivity.HEALTH
    return None


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
        if event.type in BIRTH_EVENT_TYPES and event.date_latest is not None:
            births.append(event.date_latest)
    if births and max(births) < _years_before(today, LIVING_HORIZON_YEARS):
        return LivingStatus.UNKNOWN
    return LivingStatus.LIVING


def treated_as_living(living_status: str) -> bool:
    return living_status == LivingStatus.LIVING.value


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


def person_ids(values: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    """Deduplicate while keeping order."""
    return list(dict.fromkeys(values))
