"""The `revision` audit trail: one row for every write."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

from family_history.models import Revision
from family_history.models.enums import RevisionAction
from family_history.services.access import SpaceContext


def jsonable(value: Any) -> Any:
    """Convert a value to something JSONB stores without loss of meaning."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [jsonable(v) for v in value]
    return value


def changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """`{field: {"from": old, "to": new}}` for every field whose value changed."""
    diff: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old, new = jsonable(before.get(key)), jsonable(after.get(key))
        if old != new:
            diff[key] = {"from": old, "to": new}
    return diff


def record(
    ctx: SpaceContext,
    entity_type: str,
    entity_id: uuid.UUID,
    action: RevisionAction,
    diff: Mapping[str, Any],
) -> Revision:
    revision = Revision(
        family_space_id=ctx.space_id,
        actor_sub=ctx.sub,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action.value,
        diff=jsonable(dict(diff)),
    )
    ctx.db.add(revision)
    return revision
