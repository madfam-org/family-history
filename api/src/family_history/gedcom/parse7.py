"""Read FamilySearch GEDCOM 7.0 data streams.

``parse_gedcom7(data, strict=True)`` raises `GedcomStrictError` listing every specification
violation (with line numbers). ``strict=False`` (the default) never raises on malformed input:
it repairs what it can, keeps everything it cannot interpret in generic structures, and reports
each problem as a warning.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from family_history.gedcom.charsets import decode_gedcom7
from family_history.gedcom.diagnostics import Diagnostic, Diagnostics, Severity
from family_history.gedcom.lines import DEFAULT_MAX_DEPTH, GEDCOM7, build_structures, tokenize
from family_history.gedcom.model import GedcomDocument
from family_history.gedcom.structure import Structure
from family_history.gedcom.validate import undocumented_extension_tags, validate_structures


@dataclass(slots=True)
class ParseResult:
    """A parsed document plus everything the reader noticed."""

    document: GedcomDocument
    structures: list[Structure]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    extension_tags: Counter[str] = field(default_factory=Counter)

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is not Severity.INFO]


def read_structures(
    data: bytes | str, diagnostics: Diagnostics, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> list[Structure]:
    """Decode, tokenize and assemble a 7.0 stream into level-0 structures."""
    decoded = decode_gedcom7(data, diagnostics)
    lines = tokenize(decoded.text, diagnostics, GEDCOM7)
    return build_structures(lines, diagnostics, GEDCOM7, max_depth=max_depth)


def extension_tag_counts(roots: list[Structure]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for root in roots:
        for node in root.walk():
            if node.is_extension:
                counts[node.tag] += 1
    return counts


def parse_gedcom7(
    data: bytes | str, *, strict: bool = False, max_depth: int = DEFAULT_MAX_DEPTH
) -> ParseResult:
    """Parse a GEDCOM 7.0 stream into a typed `GedcomDocument`."""
    diagnostics = Diagnostics(strict=strict)
    roots = read_structures(data, diagnostics, max_depth=max_depth)
    validate_structures(roots, diagnostics)
    undocumented = undocumented_extension_tags(roots)
    if undocumented:
        listed = ", ".join(f"{tag} x{count}" for tag, count in sorted(undocumented.items()))
        diagnostics.info("undocumented-extensions", f"extension tags not in SCHMA: {listed}")
    if strict:
        diagnostics.raise_if_errors()
    document = GedcomDocument.from_structures(roots)
    return ParseResult(document, roots, list(diagnostics), extension_tag_counts(roots))
