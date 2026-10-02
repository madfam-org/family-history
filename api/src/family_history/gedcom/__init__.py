"""GEDCOM 7.0 and 5.5.1 engine: pure, stdlib-only, no filesystem or network I/O.

Entry points:

* `parse_gedcom7` reads FamilySearch GEDCOM 7.0 (strict or tolerant);
* `import_gedcom551` reads GEDCOM 5.5.1 / 5.5 tolerantly and upgrades it to the 7.0 model;
* `write_gedcom7` and `write_gedcom551` write deterministic bytes;
* `read_gedzip`, `iter_gedzip`, `write_gedzip` and `build_gedzip` handle ``.gdz`` archives;
* `family_history.gedcom.mexico` maps Mexican family-history concepts to GEDCOM structures.

See docs/GEDCOM.md for the support matrix and docs/lanes/gedcom.md for the API notes.
"""

from family_history.gedcom.diagnostics import (
    Diagnostic,
    GedcomError,
    GedcomStrictError,
    GedcomSyntaxError,
    Severity,
)
from family_history.gedcom.extensions import MADFAM_EXTENSIONS, ExtensionTag
from family_history.gedcom.gedzip import (
    GedzipBuild,
    GedzipContents,
    GedzipError,
    GedzipLimits,
    build_gedzip,
    iter_gedzip,
    read_gedzip,
    write_gedzip,
)
from family_history.gedcom.model import (
    Family,
    GedcomDocument,
    Header,
    Individual,
    Multimedia,
    Repository,
    SharedNote,
    Source,
    Submitter,
)
from family_history.gedcom.parse7 import ParseResult, parse_gedcom7
from family_history.gedcom.parse551 import ImportReport, ImportResult, import_gedcom551
from family_history.gedcom.structure import VOID, Structure
from family_history.gedcom.write7 import write_gedcom7, write_gedcom7_text
from family_history.gedcom.write551 import Export551, write_gedcom551

__all__ = [
    "MADFAM_EXTENSIONS",
    "VOID",
    "Diagnostic",
    "Export551",
    "ExtensionTag",
    "Family",
    "GedcomDocument",
    "GedcomError",
    "GedcomStrictError",
    "GedcomSyntaxError",
    "GedzipBuild",
    "GedzipContents",
    "GedzipError",
    "GedzipLimits",
    "Header",
    "ImportReport",
    "ImportResult",
    "Individual",
    "Multimedia",
    "ParseResult",
    "Repository",
    "Severity",
    "SharedNote",
    "Source",
    "Structure",
    "Submitter",
    "build_gedzip",
    "import_gedcom551",
    "iter_gedzip",
    "parse_gedcom7",
    "read_gedzip",
    "write_gedcom551",
    "write_gedcom7",
    "write_gedcom7_text",
    "write_gedzip",
]
