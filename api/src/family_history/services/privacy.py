"""Privacy rules from docs/PRIVACY.md that the API enforces on every read.

- Living status comes from `family_history.domain.living` (services/living.py keeps it current).
- `living` and `unknown` people are private by default (treated as living).
- `private` people are visible only to their creator.
- Sensitive facts (events or assertions with a sensitivity class) about people treated as living
  are visible only to whoever recorded them, until consent flows exist.
- Default sensitivity classes come from `family_history.domain.sensitivity`.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, or_

from family_history.domain import sensitivity as domain_sensitivity
from family_history.domain.events import EventType
from family_history.models import Person
from family_history.models.enums import LivingStatus, Sensitivity, Visibility


def _api_class(value: domain_sensitivity.Sensitivity) -> Sensitivity | None:
    if value is domain_sensitivity.Sensitivity.NONE:
        return None
    return Sensitivity(value.value)


def default_sensitivity(event_type: str) -> Sensitivity | None:
    """Sacraments (including religious marriage) default to `religion`."""
    return _api_class(domain_sensitivity.default_sensitivity(EventType(event_type)))


def default_field_sensitivity(field: str) -> Sensitivity | None:
    """Assertion fields named after a `FactKind` (cause of death, medical note, ...)."""
    try:
        kind = domain_sensitivity.FactKind(field)
    except ValueError:
        return None
    return _api_class(domain_sensitivity.default_sensitivity(kind))


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
