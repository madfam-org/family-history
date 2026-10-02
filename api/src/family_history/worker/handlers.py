"""What a job does: build an export of what its creator may see, or import a file for them.

Handlers run inside the worker's transaction, under the creator's row-level-security scope, and
raise `JobFailure` with a stable code for anything the creator should be told about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from family_history.interchange import gedcom_out, native
from family_history.interchange.gedcom_in import GedcomImportError, Report, tree_from_gedcom
from family_history.interchange.gedcom_map import PRODUCT
from family_history.interchange.persist import PersistError, persist_tree
from family_history.interchange.snapshot import load_tree
from family_history.models import Job
from family_history.models.enums import ExportFormat, Role
from family_history.services.access import SpaceContext
from family_history.services.living import today_mexico_city

MEDIA_TYPES = {
    ExportFormat.GEDCOM7: "text/vnd.familysearch.gedcom",
    ExportFormat.GEDZIP: "application/vnd.familysearch.gedcom+zip",
    ExportFormat.GEDCOM551: "application/octet-stream",
    ExportFormat.NATIVE_JSON: "application/json",
}
SUFFIXES = {
    ExportFormat.GEDCOM7: ".ged",
    ExportFormat.GEDZIP: ".gdz",
    ExportFormat.GEDCOM551: "-gedcom551.ged",
    ExportFormat.NATIVE_JSON: ".json",
}


#: The job `error_code` for a `.json` upload that is not a valid `family-history-tree/v1` export.
NATIVE_INVALID = "native_export_invalid"


class JobFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Outcome:
    report: dict[str, Any]
    result: bytes | None = None
    media_type: str | None = None
    filename: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def run_export(ctx: SpaceContext, job: Job) -> Outcome:
    try:
        fmt = ExportFormat(str((job.params or {}).get("format", "")))
    except ValueError as exc:
        raise JobFailure("invalid_format", "The export format is not known.") from exc
    tree = load_tree(ctx)
    warnings: list[dict[str, Any]] = []
    if fmt is ExportFormat.NATIVE_JSON:
        data = native.export_bytes(tree)
    else:
        writer = {
            ExportFormat.GEDCOM7: gedcom_out.export_gedcom7,
            ExportFormat.GEDZIP: gedcom_out.export_gedzip,
            ExportFormat.GEDCOM551: gedcom_out.export_gedcom551,
        }[fmt]
        exported = writer(tree)
        data, warnings = exported.data, exported.warnings
    stamp = today_mexico_city().isoformat()
    diagnostics = [
        {
            "severity": "warning",
            "code": w.get("code"),
            "message": w.get("message"),
            "line": w.get("line"),
        }  # fmt: skip
        for w in warnings[:500]
    ]
    return Outcome(
        report={"format": fmt.value, "record_counts": tree.counts(), "diagnostics": diagnostics},
        result=data,
        media_type=MEDIA_TYPES[fmt],
        filename=f"family-history-{stamp}{SUFFIXES[fmt]}",
    )


def run_import(ctx: SpaceContext, job: Job) -> Outcome:
    if not ctx.can(Role.EDITOR):
        raise JobFailure("insufficient_role", "Importing needs the editor role or higher.")
    data = bytes(job.input or b"")
    if not data:
        raise JobFailure("empty_file", "The uploaded file is gone or empty.")
    if data.lstrip()[:1] == b"{":
        try:
            tree = native.to_tree(native.parse(data))
        except ValidationError as exc:
            raise JobFailure(
                NATIVE_INVALID, "The file is not a valid family-history-tree/v1 export."
            ) from exc
        report = Report(source_version=native.FORMAT, source_product=PRODUCT, container="json")
        report.record_counts = tree.counts()
    else:
        try:
            tree, report = tree_from_gedcom(data)
        except GedcomImportError as exc:
            raise JobFailure(exc.code, str(exc)) from exc
    try:
        persisted = persist_tree(ctx, tree, source=report.container)
    except PersistError as exc:
        raise JobFailure(NATIVE_INVALID, str(exc)) from exc
    return Outcome(report=report.as_dict(persisted.counts))
