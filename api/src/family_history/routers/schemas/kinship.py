"""Kinship, compadrazgo and associations."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from family_history.domain.compadrazgo import CompadrazgoRole, Occasion
from family_history.domain.kinship import KinshipKind, PartnerStatus
from family_history.models.enums import AssociationRole
from family_history.routers.schemas.common import ApiModel, InputModel, UtcDateTime

Phrase = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class KinshipStructure(ApiModel):
    """What `to` is to the person (`domain.kinship.Kinship`). `up`/`down` are generations to the
    common ancestor; `half` is null when unknown; `via` is the partner or parent an in-law or
    step relation goes through."""

    kind: KinshipKind
    up: int
    down: int
    half: bool | None
    adoptive: bool
    partner_status: PartnerStatus | None
    via: uuid.UUID | None


class KinshipOut(ApiModel):
    kinship: KinshipStructure
    label_es: str = Field(description="«tía abuela», «primo segundo», «cuñada».")
    label_en: str


class CompadrazgoItem(ApiModel):
    person_id: uuid.UUID
    display_name: str
    relation: CompadrazgoRole = Field(description="What that person is to this one.")
    sacrament: Occasion
    label_es: str = Field(description="«madrina de bautizo», «compadre de boda».")
    label_en: str


class CompadrazgoList(ApiModel):
    items: list[CompadrazgoItem]


class AssociationCreate(InputModel):
    """`person_id` took part in someone else's event: the padrino at a baptism, a witness at a
    civil marriage. The godchild is the event's principal. `other` needs a `phrase`."""

    event_id: uuid.UUID
    person_id: uuid.UUID
    role: AssociationRole
    phrase: Phrase | None = None

    @model_validator(mode="after")
    def _other_has_phrase(self) -> AssociationCreate:
        if self.role is AssociationRole.OTHER and not self.phrase:
            raise ValueError("role other needs a phrase")
        return self


class Association(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    event_id: uuid.UUID
    person_id: uuid.UUID
    role: AssociationRole
    phrase: str | None
    created_at: UtcDateTime
