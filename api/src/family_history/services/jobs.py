"""Job submission and reads for the API; the worker (family_history.worker) runs them."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_history.auth import Principal
from family_history.errors import APIError, not_found
from family_history.models import Job
from family_history.models.enums import ExportFormat, JobKind, JobStatus
from family_history.models.job import MAX_INPUT_BYTES
from family_history.services.access import SpaceContext, enter_space, user_scoped

IMPORT_SUFFIXES = {".ged": "ged", ".gdz": "gdz", ".json": "native_json"}
# Media types a browser or client may send for those files; anything else is `415`.
IMPORT_MEDIA_TYPES = frozenset(
    {
        "",
        "application/octet-stream",
        "text/plain",
        "text/vnd.familysearch.gedcom",
        "application/x-gedcom",
        "application/zip",
        "application/x-zip-compressed",
        "application/vnd.familysearch.gedcom+zip",
        "application/json",
    }
)
_CHUNK = 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _suffix(filename: str) -> str:
    match = re.search(r"\.[A-Za-z0-9]+$", filename)
    return match.group(0).lower() if match else ""


async def read_upload(upload: UploadFile) -> tuple[bytes, str]:
    """The upload's bytes (at most 25 MiB) and its detected container."""
    container = IMPORT_SUFFIXES.get(_suffix(upload.filename or ""))
    media_type = (upload.content_type or "").split(";")[0].strip().lower()
    if container is None or media_type not in IMPORT_MEDIA_TYPES:
        raise APIError(415, "unsupported_file", "Upload a .ged, .gdz or family-history .json file.")
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > MAX_INPUT_BYTES:
            raise APIError(413, "file_too_large", "The file is larger than 25 MiB.")
        chunks.append(chunk)
    if size == 0:
        raise APIError(422, "empty_file", "The file is empty.")
    return b"".join(chunks), container


def submit(
    ctx: SpaceContext, kind: JobKind, params: dict[str, str], data: bytes | None = None
) -> Job:
    job = Job(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        kind=kind.value,
        status=JobStatus.QUEUED.value,
        params=params,
        input=data,
        report={},
        attempts=0,
        created_by=ctx.sub,
        created_at=datetime.now(UTC),
    )
    ctx.db.add(job)
    ctx.db.commit()
    return job


def import_params(filename: str | None, container: str) -> dict[str, str]:
    safe = _SAFE_NAME.sub("_", filename or "upload")[:120]
    return {"filename": safe, "container": container}


def export_params(fmt: ExportFormat) -> dict[str, str]:
    return {"format": fmt.value}


def own_job(db: Session, principal: Principal, job_id: uuid.UUID) -> Job:
    """The caller's own job (RLS shows nobody else's), in a space they still belong to."""
    user_scoped(db, principal)
    job = db.scalar(select(Job).where(Job.id == job_id, Job.created_by == principal.sub))
    if job is None:
        raise not_found("job_not_found", "Job not found.")
    enter_space(db, principal, job.family_space_id)
    return job
