"""GEDCOM 5.5.1 writer, for families moving to legacy desktop tools.

The output is UTF-8 (``HEAD.CHAR UTF-8``), with 255-character lines split by ``CONC`` and
every ``@`` doubled outside date escapes. 7.0 constructs that 5.5.1 cannot express are kept
under underscore tags and listed in the export report; see `family_history.gedcom.downgrade551`
and docs/GEDCOM.md for every rule. The same document always yields the same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from family_history.gedcom.diagnostics import Diagnostic, Diagnostics
from family_history.gedcom.downgrade551 import Downgrader
from family_history.gedcom.emit import GEDCOM551_EMIT, emit_lines, render
from family_history.gedcom.model import GedcomDocument


@dataclass(slots=True)
class Export551:
    """The 5.5.1 bytes and the report of everything that was converted or marked."""

    data: bytes
    report: list[Diagnostic] = field(default_factory=list)


def write_gedcom551(
    document: GedcomDocument, *, line_ending: str = "\r\n", bom: bool = False
) -> Export551:
    """Write ``document`` as GEDCOM 5.5.1.

    CR-LF is the default line ending because most legacy readers were written for Windows;
    the byte-order mark is off by default because several of them reject it.
    """
    if line_ending not in ("\n", "\r\n", "\r"):
        raise ValueError("line_ending must be LF, CR-LF or CR")
    diagnostics = Diagnostics(strict=False)
    roots = Downgrader(diagnostics).run(document.to_structures())
    text = render(emit_lines(roots, GEDCOM551_EMIT), line_ending)
    data = ("\ufeff" + text if bom else text).encode("utf-8")
    return Export551(data, list(diagnostics))
