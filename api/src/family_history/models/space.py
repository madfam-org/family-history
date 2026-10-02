"""Family spaces (the RLS tenant) and their members."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from family_history.models.base import Base, IdMixin, TimestampMixin
from family_history.models.enums import Role, sql_in


class FamilySpace(IdMixin, TimestampMixin, Base):
    __tablename__ = "family_space"

    name: Mapped[str] = mapped_column(String(200))
    janua_organization_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_by: Mapped[str] = mapped_column(String(255))


class SpaceMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "space_member"
    __table_args__ = (
        UniqueConstraint("family_space_id", "user_sub"),
        CheckConstraint(sql_in("role", Role), name="role"),
        Index("ix_space_member_user_sub", "user_sub"),
    )

    family_space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("family_space.id", ondelete="CASCADE")
    )
    user_sub: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
