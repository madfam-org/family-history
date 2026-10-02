"""Family spaces, members and the caller."""

from __future__ import annotations

import uuid

from family_history.models.enums import Role
from family_history.routers.schemas.common import ApiModel, InputModel, ShortText, UtcDateTime


class SpaceSummary(ApiModel):
    id: uuid.UUID
    name: str
    role: Role
    people_count: int


class Space(SpaceSummary):
    janua_organization_id: str | None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class SpaceCreate(InputModel):
    name: ShortText


class SpaceRename(InputModel):
    name: ShortText


class Member(ApiModel):
    user_sub: str
    role: Role
    created_at: UtcDateTime


class Me(ApiModel):
    sub: str
    email: str | None
    name: str | None
    early_access: bool
    spaces: list[SpaceSummary]
