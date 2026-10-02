"""Imports, exports and their jobs. A Postgres-backed queue (docs/adr/0002) runs them."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, APIError, conflict
from family_history.models.enums import JobKind, JobStatus, Role
from family_history.routers.schemas.jobs import ExportRequest, Job, JobAccepted
from family_history.services import jobs as job_service
from family_history.services.access import DbSession, SpaceCtx

router = APIRouter(prefix="/v1", tags=["jobs"], responses=ERROR_RESPONSES)

_DOWNLOAD_CHUNK = 64 * 1024


@router.post(
    "/spaces/{space_id}/imports",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_import(
    ctx: SpaceCtx, file: Annotated[UploadFile, File(description=".ged, .gdz or .json")]
) -> JobAccepted:
    """Import a GEDCOM 7 or 5.5.1 file (`.ged`, version auto-detected), a GEDZIP (`.gdz`; media
    entries are skipped with a warning) or a native `family-history-tree/v1` export (`.json`),
    up to 25 MiB (`413 file_too_large`; other files `415 unsupported_file`). Stewards and
    editors only. Poll `GET /v1/jobs/{job_id}`: an unreadable file fails the job with
    `gedcom_invalid` or `native_export_invalid`."""
    ctx.require(Role.EDITOR)
    data, container = await job_service.read_upload(file)
    params = job_service.import_params(file.filename, container)
    job = job_service.submit(ctx, JobKind.GEDCOM_IMPORT, params, data)
    return JobAccepted(job_id=job.id)


@router.post(
    "/spaces/{space_id}/exports",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export(body: ExportRequest, ctx: SpaceCtx) -> JobAccepted:
    """Export what the caller can see. Any member may export: the exit is free at every tier."""
    job = job_service.submit(ctx, JobKind.EXPORT, job_service.export_params(body.format))
    return JobAccepted(job_id=job.id)


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession) -> Job:
    """The caller's own job. Jobs are private to whoever submitted them."""
    job = job_service.own_job(db, principal, job_id)
    return Job(
        id=job.id,
        kind=JobKind(job.kind),
        status=JobStatus(job.status),
        report=dict(job.report or {}),
        error_code=job.error_code,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get(
    "/jobs/{job_id}/download",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "The export file."},
        410: {"description": "The result expired (24 hours after the job finished)."},
    },
)
def download(
    job_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> StreamingResponse:
    """The export file. `409 job_not_ready` until it succeeds, `410 download_expired` 24 hours
    after it finished."""
    job = job_service.own_job(db, principal, job_id)
    if job.kind != JobKind.EXPORT.value:
        raise conflict("no_download", "Only export jobs have a file to download.")
    if job.status != JobStatus.SUCCEEDED.value:
        raise conflict("job_not_ready", "The export has not finished.")
    expired = job.expires_at is not None and job.expires_at <= datetime.now(UTC)
    if expired or job.result is None:
        raise APIError(410, "download_expired", "The export expired; request a new one.")
    payload = bytes(job.result)
    filename = job.result_filename or "family-history-export"

    def chunks() -> Iterator[bytes]:
        for start in range(0, len(payload), _DOWNLOAD_CHUNK):
            yield payload[start : start + _DOWNLOAD_CHUNK]

    return StreamingResponse(
        chunks(),
        media_type=job.result_media_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )
