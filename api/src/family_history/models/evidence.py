"""Sources, citations and append-only assertions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from family_history.models.base import (
    AuthoredMixin,
    Base,
    IdMixin,
    TenantMixin,
    TimestampMixin,
    utcnow,
)
from family_history.models.enums import (
    AssertionStatus,
    Sensitivity,
    SourceType,
    SubjectType,
    sql_in,
)


class Source(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    __tablename__ = "source"
    __table_args__ = (
        UniqueConstraint("family_space_id", "id"),
        CheckConstraint(sql_in("type", SourceType), name="type"),
        Index("ix_source_space_title", "family_space_id", "title"),
    )

    type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(500))
    repository: Mapped[str | None] = mapped_column(String(500))
    # Typed locator, e.g. {"libro": "12", "parroquia": "..."} for a parish book.
    locator: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Citation(IdMixin, TimestampMixin, TenantMixin, AuthoredMixin, Base):
    __tablename__ = "citation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["family_space_id", "source_id"],
            ["source.family_space_id", "source.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("quality BETWEEN 0 AND 3", name="quality"),
        Index("ix_citation_source", "family_space_id", "source_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column()
    page: Mapped[str | None] = mapped_column(String(100))
    foja: Mapped[str | None] = mapped_column(String(100))
    partida: Mapped[str | None] = mapped_column(String(100))
    quality: Mapped[int | None] = mapped_column(SmallInteger)
    extracted_text: Mapped[str | None] = mapped_column(Text)


class Assertion(IdMixin, TenantMixin, Base):
    """A fact with provenance. Rows are never updated or deleted: a change of status or of
    citations is a new row whose `supersedes_id` points at the previous one. RLS grants only
    SELECT and INSERT on this table."""

    __tablename__ = "assertion"
    __table_args__ = (
        CheckConstraint(sql_in("subject_type", SubjectType), name="subject_type"),
        CheckConstraint(sql_in("status", AssertionStatus), name="status"),
        CheckConstraint(
            f"sensitivity IS NULL OR {sql_in('sensitivity', Sensitivity)}", name="sensitivity"
        ),
        UniqueConstraint("supersedes_id"),
        Index("ix_assertion_subject", "family_space_id", "subject_type", "subject_id"),
    )

    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[uuid.UUID] = mapped_column()
    field: Mapped[str] = mapped_column(String(100))
    value: Mapped[Any] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    asserted_by: Mapped[str] = mapped_column(String(255))
    citation_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assertion.id", ondelete="RESTRICT")
    )
    sensitivity: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
