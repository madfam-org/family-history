"""Family spaces, members and the caller."""

from __future__ import annotations

import uuid
from datetime import datetime

from family_history.models.enums import Role
from family_history.routers.schemas.common import ApiModel, InputModel, ShortText


class SpaceSummary(ApiModel):
    id: uuid.UUID
    name: str
    role: Role
    people_count: int


class Space(SpaceSummary):
    janua_organization_id: str | None
    created_at: datetime
    updated_at: datetime


class SpaceCreate(InputModel):
    name: ShortText


class SpaceRename(InputModel):
    name: ShortText


class Member(ApiModel):
    user_sub: str
    role: Role
    created_at: datetime


class Me(ApiModel):
    sub: str
    email: str | None
    name: str | None
    early_access: bool
    spaces: list[SpaceSummary]
