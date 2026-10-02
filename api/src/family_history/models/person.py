"""People, their name forms and the relationship graph."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from family_history.models.base import AuthoredMixin, Base, IdMixin, TenantMixin, TimestampMixin
from family_history.models.enums import (
    LivingStatus,
    PartnerStatus,
    Pedigree,
    RelationshipType,
    Sex,
    SurnameOrder,
    Visibility,
    sql_in,
)


class Person(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    __tablename__ = "person"
    __table_args__ = (
        UniqueConstraint("family_space_id", "id"),
        CheckConstraint(sql_in("sex", Sex), name="sex"),
        CheckConstraint(sql_in("living_status", LivingStatus), name="living_status"),
        CheckConstraint(sql_in("visibility", Visibility), name="visibility"),
        Index("ix_person_space_sort", "family_space_id", "sort_name", "id"),
    )

    sex: Mapped[str] = mapped_column(String(1), default=Sex.U.value)
    living_status: Mapped[str] = mapped_column(String(20), default=LivingStatus.UNKNOWN.value)
    visibility: Mapped[str] = mapped_column(String(20), default=Visibility.SPACE.value)
    # Maintained by the application from every name form: lowercase, accents stripped.
    search_text: Mapped[str] = mapped_column(Text, default="")
    sort_name: Mapped[str] = mapped_column(Text, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)

    names: Mapped[list[NameForm]] = relationship(
        back_populates="person",
        cascade="all, delete-orphan",
        order_by="NameForm.position",
        lazy="selectin",
    )


class NameForm(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "name_form"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_space_id", "person_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(sql_in("surname_order", SurnameOrder), name="surname_order"),
        Index("ix_name_form_person", "person_id", "position"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer, default=0)
    given: Mapped[str | None] = mapped_column(String(200))
    apellido_paterno: Mapped[str | None] = mapped_column(String(200))
    apellido_materno: Mapped[str | None] = mapped_column(String(200))
    extra_surnames: Mapped[list[str]] = mapped_column(default=list)
    # {"paterno": "de la", "materno": "del"}: particles that precede each surname.
    particles: Mapped[dict[str, Any]] = mapped_column(default=dict)
    nombre_de_pila: Mapped[str | None] = mapped_column(String(200))
    nombre_usado: Mapped[str | None] = mapped_column(String(200))
    nicknames: Mapped[list[str]] = mapped_column(default=list)
    name_type: Mapped[str] = mapped_column(String(20), default="birth")
    lang: Mapped[str] = mapped_column(String(35), default="es-MX")
    surname_order: Mapped[str] = mapped_column(
        String(20), default=SurnameOrder.PATERNO_MATERNO.value
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    person: Mapped[Person] = relationship(back_populates="names")


_KIND_CHECK = (
    f"(type = 'parent_child' AND {sql_in('pedigree', Pedigree)} AND partner_status IS NULL)"
    f" OR (type = 'union' AND {sql_in('partner_status', PartnerStatus)} AND pedigree IS NULL)"
)


class Relationship(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    """A graph edge. For `parent_child`, `from_person_id` is the parent and `pedigree` says how
    the child is linked; a `union` carries its `partner_status`."""

    __tablename__ = "relationship"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_space_id", "from_person_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["family_space_id", "to_person_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(sql_in("type", RelationshipType), name="type"),
        CheckConstraint(_KIND_CHECK, name="kind"),
        CheckConstraint("from_person_id <> to_person_id", name="not_self"),
        Index("ix_relationship_from", "family_space_id", "from_person_id"),
        Index("ix_relationship_to", "family_space_id", "to_person_id"),
    )

    type: Mapped[str] = mapped_column(String(20))
    from_person_id: Mapped[uuid.UUID] = mapped_column()
    to_person_id: Mapped[uuid.UUID] = mapped_column()
    pedigree: Mapped[str | None] = mapped_column(String(20))
    partner_status: Mapped[str | None] = mapped_column(String(20))

    @property
    def qualifier(self) -> str:
        """The v1 API's single `qualifier`: the pedigree or the partner status."""
        return self.pedigree or self.partner_status or ""
