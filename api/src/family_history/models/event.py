"""Events, their participants, godparent associations and the place hierarchy."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from family_history.models.base import AuthoredMixin, Base, IdMixin, TenantMixin, TimestampMixin
from family_history.models.enums import (
    AssociationRole,
    ParticipantRole,
    PlaceKind,
    Sensitivity,
    sql_in,
)


class Place(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    """A time-aware place. `valid_from`/`valid_to` bound the period the name and parent held."""

    __tablename__ = "place"
    __table_args__ = (
        UniqueConstraint("family_space_id", "id"),
        ForeignKeyConstraint(
            ["family_space_id", "parent_id"], ["place.family_space_id", "place.id"]
        ),
        CheckConstraint(sql_in("kind", PlaceKind), name="kind"),
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to", name="validity"
        ),
    )

    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[uuid.UUID | None] = mapped_column()
    valid_from: Mapped[date | None] = mapped_column()
    valid_to: Mapped[date | None] = mapped_column()
    inegi_code: Mapped[str | None] = mapped_column(String(20))
    search_text: Mapped[str] = mapped_column(Text, default="")


class Event(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    __tablename__ = "event"
    __table_args__ = (
        UniqueConstraint("family_space_id", "id"),
        ForeignKeyConstraint(
            ["family_space_id", "place_id"], ["place.family_space_id", "place.id"]
        ),
        CheckConstraint(
            f"sensitivity IS NULL OR {sql_in('sensitivity', Sensitivity)}", name="sensitivity"
        ),
        Index("ix_event_space_type", "family_space_id", "type"),
    )

    type: Mapped[str] = mapped_column(String(50))
    # GEDCOM 7 DateValue text as entered; the domain library computes the bounds.
    date_value: Mapped[str | None] = mapped_column(String(100))
    date_earliest: Mapped[date | None] = mapped_column()
    date_latest: Mapped[date | None] = mapped_column()
    place_id: Mapped[uuid.UUID | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str | None] = mapped_column(String(20))


class EventParticipant(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "event_participant"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_space_id", "event_id"],
            ["event.family_space_id", "event.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["family_space_id", "person_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("event_id", "person_id", "role"),
        CheckConstraint(sql_in("role", ParticipantRole), name="role"),
        Index("ix_event_participant_person", "family_space_id", "person_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column()
    person_id: Mapped[uuid.UUID] = mapped_column()
    role: Mapped[str] = mapped_column(String(20))


class Association(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    """A godparent (or witness) tie made at a sacrament. Compadrazgo is derived, never stored."""

    __tablename__ = "association"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_space_id", "event_id"],
            ["event.family_space_id", "event.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["family_space_id", "person_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["family_space_id", "associate_id"],
            ["person.family_space_id", "person.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("event_id", "person_id", "associate_id", "role"),
        CheckConstraint(sql_in("role", AssociationRole), name="role"),
        CheckConstraint("person_id <> associate_id", name="not_self"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column()
    person_id: Mapped[uuid.UUID] = mapped_column()
    associate_id: Mapped[uuid.UUID] = mapped_column()
    role: Mapped[str] = mapped_column(String(20), default=AssociationRole.GODPARENT.value)
