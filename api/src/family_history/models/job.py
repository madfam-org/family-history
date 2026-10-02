"""The Postgres-backed job queue (docs/adr/0002-postgres-job-queue.md).

A job is a tenant row: the API inserts it for the caller, the worker claims it with
`FOR UPDATE SKIP LOCKED` and runs it under the caller's own row-level-security scope. Inputs and
results live in the row (bytea), so the worker needs nothing but `DATABASE_URL`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, LargeBinary, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from family_history.models.base import Base, IdMixin, TenantMixin, utcnow
from family_history.models.enums import JobKind, JobStatus, sql_in

MAX_INPUT_BYTES = 25 * 1024 * 1024


class Job(IdMixin, TenantMixin, Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(sql_in("kind", JobKind), name="kind"),
        CheckConstraint(sql_in("status", JobStatus), name="status"),
        CheckConstraint(
            f"input IS NULL OR octet_length(input) <= {MAX_INPUT_BYTES}", name="input_size"
        ),
        Index("ix_job_queue", "status", "created_at"),
        Index("ix_job_creator", "family_space_id", "created_by", "created_at"),
    )

    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED.value)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    input: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    result: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    result_media_type: Mapped[str | None] = mapped_column(String(100))
    result_filename: Mapped[str | None] = mapped_column(String(200))
    report: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error_code: Mapped[str | None] = mapped_column(String(50))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
