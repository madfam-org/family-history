"""Tolerant GEDCOM 5.5.1 import, upgraded to the 7.0 model.

``import_gedcom551(data)`` never raises on malformed input. It returns a 7.0-shaped
`GedcomDocument` and an `ImportReport`: record counts per (5.5.1) record type, every
diagnostic with its line number, the extension tags seen, and the cross-reference ids that
had to be rewritten.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from family_history.gedcom.charsets import decode_gedcom551
from family_history.gedcom.diagnostics import Diagnostic, Diagnostics, Severity
from family_history.gedcom.lines import DEFAULT_MAX_DEPTH, GEDCOM551, build_structures, tokenize
from family_history.gedcom.model import GedcomDocument
from family_history.gedcom.parse7 import extension_tag_counts
from family_history.gedcom.structure import Structure
from family_history.gedcom.upgrade551 import Upgrader
from family_history.gedcom.validate import validate_structures


@dataclass(slots=True)
class ImportReport:
    """What happened while importing a 5.5.1 file."""

    source_version: str | None
    source_product: str | None
    encoding: str
    declared_charset: str | None
    record_counts: dict[str, int] = field(default_factory=dict)
    created_records: dict[str, int] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    extension_tags: dict[str, int] = field(default_factory=dict)
    renamed_xrefs: dict[str, str] = field(default_factory=dict)

    @property
    def warnings(self) -> list[Diagnostic]:
        """Diagnostics that may have changed meaning (everything but info notes)."""
        return [d for d in self.diagnostics if d.severity is not Severity.INFO]

    def codes(self) -> Counter[str]:
        """How many diagnostics of each code were recorded."""
        return Counter(d.code for d in self.diagnostics)


@dataclass(slots=True)
class ImportResult:
    document: GedcomDocument
    report: ImportReport
    structures: list[Structure]


def read_structures551(
    data: bytes | str, diagnostics: Diagnostics, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> tuple[list[Structure], str, str | None]:
    """Decode and assemble a 5.5.1 stream; returns roots, encoding and declared charset."""
    decoded = decode_gedcom551(data, diagnostics)
    lines = tokenize(decoded.text, diagnostics, GEDCOM551)
    roots = build_structures(lines, diagnostics, GEDCOM551, max_depth=max_depth)
    return roots, decoded.encoding, decoded.declared


def import_gedcom551(data: bytes | str, *, max_depth: int = DEFAULT_MAX_DEPTH) -> ImportResult:
    """Import a GEDCOM 5.5.1 (or 5.5) file into the 7.0 model. Never raises on bad input."""
    diagnostics = Diagnostics(strict=False)
    roots, encoding, declared = read_structures551(data, diagnostics, max_depth=max_depth)
    head = next((r for r in roots if r.tag == "HEAD"), None)
    gedc = head.first("GEDC") if head is not None else None
    version = gedc.text("VERS") if gedc is not None else None
    product = head.text("SOUR") if head is not None else None
    if version is not None and not version.startswith("5."):
        diagnostics.warning(
            "version", f"HEAD.GEDC.VERS is {version!r}, not 5.x; imported as 5.5.1 anyway", 1
        )
    counts = Counter(r.tag for r in roots if r.tag not in ("HEAD", "TRLR"))
    upgrader = Upgrader(diagnostics)
    upgraded = upgrader.run(roots)
    _report_residuals(upgraded, diagnostics)
    created = Counter(r.tag for r in upgrader.new_records)
    report = ImportReport(
        source_version=version,
        source_product=product,
        encoding=encoding,
        declared_charset=declared,
        record_counts=dict(sorted(counts.items())),
        created_records=dict(sorted(created.items())),
        diagnostics=list(diagnostics),
        extension_tags=dict(sorted(extension_tag_counts(upgraded).items())),
        renamed_xrefs=dict(upgrader.renamed),
    )
    return ImportResult(GedcomDocument.from_structures(upgraded), report, upgraded)


def _report_residuals(roots: list[Structure], diagnostics: Diagnostics) -> None:
    """Validate the upgraded tree; whatever 7.0 still rejects is reported, never dropped."""
    residual = Diagnostics(strict=False)
    validate_structures(roots, residual)
    for item in residual:
        diagnostics.warning(
            f"residual-{item.code}", f"kept as found, still not valid 7.0: {item.message}",
            item.line,
        )
