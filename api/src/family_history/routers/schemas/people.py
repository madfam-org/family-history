"""People and name forms."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, model_validator

from family_history.models.enums import LivingStatus, NameType, Sex, SurnameOrder, Visibility
from family_history.routers.schemas.common import (
    ApiModel,
    EventBrief,
    InputModel,
    LangTag,
    ShortText,
    UtcDateTime,
)
from family_history.routers.schemas.events import Event, Relationship
from family_history.routers.schemas.evidence import Citation

Particle = Annotated[str, Field(min_length=1, max_length=20)]


class NameParticles(InputModel):
    """Particles that precede each surname, such as `de`, `de la` or `del`."""

    paterno: Particle | None = None
    materno: Particle | None = None


class NameFormIn(InputModel):
    given: ShortText | None = None
    apellido_paterno: ShortText | None = None
    apellido_materno: ShortText | None = None
    extra_surnames: list[ShortText] = Field(default_factory=list, max_length=6)
    particles: NameParticles = Field(default_factory=NameParticles)
    nombre_de_pila: ShortText | None = None
    nombre_usado: ShortText | None = None
    nicknames: list[ShortText] = Field(default_factory=list, max_length=10)
    name_type: NameType = NameType.BIRTH
    lang: LangTag = "es-MX"
    surname_order: SurnameOrder = SurnameOrder.PATERNO_MATERNO
    is_primary: bool = False

    @model_validator(mode="after")
    def _has_a_name(self) -> NameFormIn:
        if not any(
            (
                self.given,
                self.apellido_paterno,
                self.apellido_materno,
                self.nombre_de_pila,
                self.nombre_usado,
            )
        ):
            raise ValueError("a name form needs at least one name part")
        return self


class NameFormOut(ApiModel):
    id: uuid.UUID
    position: int
    given: str | None
    apellido_paterno: str | None
    apellido_materno: str | None
    extra_surnames: list[str]
    particles: dict[str, str]
    nombre_de_pila: str | None
    nombre_usado: str | None
    nicknames: list[str]
    name_type: NameType
    lang: str
    surname_order: SurnameOrder
    is_primary: bool


class PersonCreate(InputModel):
    sex: Sex = Sex.U
    visibility: Visibility = Visibility.SPACE
    names: list[NameFormIn] = Field(min_length=1, max_length=20)


class PersonPatch(InputModel):
    sex: Sex | None = None
    visibility: Visibility | None = None
    names: list[NameFormIn] | None = Field(default=None, min_length=1, max_length=20)


class PersonSummary(ApiModel):
    id: uuid.UUID
    display_name: str
    sex: Sex
    living_status: LivingStatus
    birth: EventBrief | None
    death: EventBrief | None
    visibility: Visibility


class PersonPage(ApiModel):
    items: list[PersonSummary]
    next_cursor: str | None


class Person(ApiModel):
    id: uuid.UUID
    space_id: uuid.UUID
    display_name: str
    sex: Sex
    living_status: LivingStatus
    visibility: Visibility
    names: list[NameFormOut]
    events: list[Event]
    relationships: list[Relationship]
    citations: list[Citation]
    created_by: str
    created_at: UtcDateTime
    updated_at: UtcDateTime
