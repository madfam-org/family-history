"""MADFAM family-history extension tags for GEDCOM 7.0.

Each tag is a documented extension: the 7.0 writer declares it in ``HEAD.SCHMA`` with the URI
below whenever a dataset uses it. The URIs point at the matching section of docs/GEDCOM.md in
the public repository and are stable identifiers: they must never be reassigned.
"""

from __future__ import annotations

from dataclasses import dataclass

URI_BASE = "https://github.com/madfam-org/family-history/blob/main/docs/GEDCOM.md#"


@dataclass(frozen=True, slots=True)
class ExtensionTag:
    tag: str
    uri: str
    meaning: str
    values: tuple[str, ...]


def _ext(tag: str, meaning: str, values: tuple[str, ...]) -> ExtensionTag:
    return ExtensionTag(tag, URI_BASE + tag.lower(), meaning, values)


SURNAME_LINE = _ext(
    "_FH_SURNAME_LINE",
    "Under NAME.SURN: which parent's line this surname comes from.",
    ("PATERNAL", "MATERNAL", "OTHER"),
)
SURNAME_ORDER = _ext(
    "_FH_SURNAME_ORDER",
    "Under NAME: the display order of the two surnames.",
    ("PATERNAL_FIRST", "MATERNAL_FIRST"),
)
SENSITIVITY = _ext(
    "_FH_SENSITIVITY",
    "Under any fact, note or CAUS: the sensitive-data classes (a List:Enum) the fact carries.",
    ("RELIGION", "HEALTH", "GENETIC", "ETHNICITY", "SEXUAL", "POLITICAL"),
)
EVENT_KIND = _ext(
    "_FH_EVENT_KIND",
    "Under EVEN or MARR: the machine-readable kind of a Mexican or binational event.",
    (
        "CIVIL_MARRIAGE",
        "RELIGIOUS_MARRIAGE",
        "FREE_UNION",
        "QUINCEANERA",
        "BRACERO_CONTRACT",
        "BORDER_CROSSING",
    ),
)

MADFAM_EXTENSIONS: dict[str, ExtensionTag] = {
    ext.tag: ext for ext in (SURNAME_LINE, SURNAME_ORDER, SENSITIVITY, EVENT_KIND)
}
