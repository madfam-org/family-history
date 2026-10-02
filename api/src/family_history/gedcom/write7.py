"""Deterministic FamilySearch GEDCOM 7.0 writer.

The same `GedcomDocument` always produces the same bytes:

* ``HEAD`` first, with ``GEDC.VERS 7.0`` as its first substructure and ``SCHMA`` right after;
* records grouped by type (SUBM, INDI, FAM, SOUR, REPO, OBJE, SNOTE, then extension records),
  each group in document order;
* within a structure, typed fields in model order, then unmodelled substructures in their
  original order;
* multi-line payloads split into ``CONT`` lines; a leading ``@`` doubled. 7.0 has no line
  length limit, so ``CONC`` is never written.

Every MADFAM extension tag used anywhere in the dataset is declared in ``HEAD.SCHMA``. Existing
tag definitions are kept; an existing definition always wins over ours for the same tag.
"""

from __future__ import annotations

from family_history.gedcom.emit import GEDCOM7_EMIT, emit_lines, render
from family_history.gedcom.extensions import MADFAM_EXTENSIONS
from family_history.gedcom.model import GedcomDocument
from family_history.gedcom.structure import Structure

GEDCOM_VERSION = "7.0"


def prepare_structures(document: GedcomDocument) -> list[Structure]:
    """The level-0 structures the writer emits, with ``GEDC`` and ``SCHMA`` normalized."""
    roots = document.to_structures()
    head = roots[0]
    used = {node.tag for root in roots for node in root.walk() if node.is_extension}
    _normalize_head(head, used)
    return roots


def _normalize_head(head: Structure, used: set[str]) -> None:
    gedc = head.first("GEDC")
    if gedc is None:
        gedc = Structure(tag="GEDC")
    head.children = [c for c in head.children if c is not gedc]
    vers = gedc.first("VERS")
    if vers is None or not (vers.payload or "").startswith("7.0"):
        gedc.children = [c for c in gedc.children if c.tag != "VERS"]
        gedc.children.insert(0, Structure(tag="VERS", payload=GEDCOM_VERSION))
    schema = head.first("SCHMA")
    head.children = [c for c in head.children if c is not schema]
    if schema is None:
        schema = Structure(tag="SCHMA")
    defined = {(t.payload or "").partition(" ")[0] for t in schema.all("TAG")}
    for tag in sorted(used & MADFAM_EXTENSIONS.keys()):
        if tag not in defined:
            definition = f"{tag} {MADFAM_EXTENSIONS[tag].uri}"
            schema.children.append(Structure(tag="TAG", payload=definition))
    head.children.insert(0, gedc)
    if schema.children:
        head.children.insert(1, schema)


def write_gedcom7_text(document: GedcomDocument, *, line_ending: str = "\n") -> str:
    """The dataset as text (no byte-order mark)."""
    if line_ending not in ("\n", "\r\n", "\r"):
        raise ValueError("line_ending must be LF, CR-LF or CR")
    return render(emit_lines(prepare_structures(document), GEDCOM7_EMIT), line_ending)


def write_gedcom7(document: GedcomDocument, *, line_ending: str = "\n", bom: bool = True) -> bytes:
    """The dataset as UTF-8 bytes, with the byte-order mark the specification recommends."""
    text = write_gedcom7_text(document, line_ending=line_ending)
    return ("\ufeff" + text if bom else text).encode("utf-8")
