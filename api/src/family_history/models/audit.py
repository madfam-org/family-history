"""The write audit trail and the public waitlist."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from family_history.models.base import Base, IdMixin, TenantMixin, utcnow


class Revision(IdMixin, TenantMixin, Base):
    """One row per write. Append-only: RLS grants only SELECT and INSERT."""

    __tablename__ = "revision"
    __table_args__ = (
        Index("ix_revision_entity", "family_space_id", "entity_type", "entity_id"),
    )

    actor_sub: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(20))
    diff: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class WaitlistEntry(IdMixin, Base):
    """A waitlist sign-up. The email is stored for the relay to PhyndCRM and is never logged."""

    __tablename__ = "waitlist_entry"
    __table_args__ = (
        Index("uq_waitlist_entry_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(254))
    locale: Mapped[str] = mapped_column(String(35))
    consent_at: Mapped[datetime] = mapped_column()
    aviso_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    relayed_at: Mapped[datetime | None] = mapped_column(default=None)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
