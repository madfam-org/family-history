"""Jobs: GEDCOM and native imports, exports."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from family_history.models.enums import ExportFormat, JobKind, JobStatus
from family_history.routers.schemas.common import ApiModel, InputModel, UtcDateTime


class JobAccepted(ApiModel):
    job_id: uuid.UUID


class ExportRequest(InputModel):
    format: ExportFormat = Field(
        description=(
            "`gedcom7` (.ged), `gedzip` (.gdz, GEDCOM 7 in a zip), `gedcom551` (.ged, legacy) or "
            "`native_json` (lossless `family-history-tree/v1`)."
        )
    )


class Job(ApiModel):
    id: uuid.UUID
    kind: JobKind
    status: JobStatus
    report: dict[str, Any] = Field(
        description=(
            "Imports: `format`, `source_version`, `counts`, `warnings` ({code, message, line}), "
            "`warnings_truncated`, `extension_tags`. Exports: `format`, `counts`, `warnings`."
        )
    )
    error_code: str | None
    created_at: UtcDateTime
    finished_at: UtcDateTime | None
