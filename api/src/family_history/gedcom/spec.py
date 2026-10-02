"""Lookup tables for FamilySearch GEDCOM 7.0.18, built from the specification's own grammar.

`STRUCTURE_TYPES` maps a structure-type URI (``g7:INDI-NAME``) to its payload rule and the
substructures it permits, keyed by tag. `RECORD_TYPES` maps level-0 tags to record URIs. The
validator walks a document against these tables, so it accepts exactly what the specification
accepts rather than a hand-maintained approximation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from family_history.gedcom.spec_grammar import GRAMMAR

HEAD_URI = "g7:HEAD"
TRLR_URI = "g7:TRLR"

INDIVIDUAL_EVENTS = frozenset(
    "ADOP BAPM BARM BASM BIRT BLES BURI CENS CHR CHRA CONF CREM DEAT EMIG FCOM GRAD IMMI NATU "
    "ORDN PROB RETI WILL".split()
)
FAMILY_EVENTS = frozenset("ANUL CENS DIV DIVF ENGA MARB MARC MARL MARR MARS".split())
INDIVIDUAL_ATTRIBUTES = frozenset(
    "CAST DSCR EDUC IDNO NATI NCHI NMR OCCU PROP RELI RESI SSN TITL FACT".split()
)
FAMILY_ATTRIBUTES = frozenset("NCHI RESI FACT".split())

ENUM_SETS: dict[str, frozenset[str]] = {
    "ADOP": frozenset({"HUSB", "WIFE", "BOTH"}),
    "EVEN": INDIVIDUAL_EVENTS | FAMILY_EVENTS,
    "EVENATTR": INDIVIDUAL_EVENTS | FAMILY_EVENTS | INDIVIDUAL_ATTRIBUTES | {"EVEN"},
    "MEDI": frozenset(
        "AUDIO BOOK CARD ELECTRONIC FICHE FILM MAGAZINE MANUSCRIPT MAP NEWSPAPER PHOTO "
        "TOMBSTONE VIDEO OTHER".split()
    ),
    "PEDI": frozenset({"ADOPTED", "BIRTH", "FOSTER", "SEALING", "OTHER"}),
    "QUAY": frozenset({"0", "1", "2", "3"}),
    "RESN": frozenset({"CONFIDENTIAL", "LOCKED", "PRIVACY"}),
    "ROLE": frozenset(
        "CHIL CLERGY FATH FRIEND GODP HUSB MOTH MULTIPLE NGHBR OFFICIATOR PARENT SPOU WIFE WITN "
        "OTHER".split()
    ),
    "SEX": frozenset({"M", "F", "X", "U"}),
    "FAMC-STAT": frozenset({"CHALLENGED", "DISPROVEN", "PROVEN"}),
    "ord-STAT": frozenset(
        "BIC CANCELED CHILD COMPLETED EXCLUDED DNS DNS_CAN INFANT PRE_1970 STILLBORN SUBMITTED "
        "UNCLEARED".split()
    ),
    "NAME-TYPE": frozenset(
        {"AKA", "BIRTH", "IMMIGRANT", "MAIDEN", "MARRIED", "PROFESSIONAL", "OTHER"}
    ),
}

#: Which enumeration set each enumeration-typed structure draws from.
ENUM_SET_OF: dict[str, str] = {
    "g7:FAMC-ADOP": "ADOP",
    "g7:NO": "EVEN",
    "g7:DATA-EVEN": "EVENATTR",
    "g7:SOUR-EVEN": "EVENATTR",
    "g7:MEDI": "MEDI",
    "g7:PEDI": "PEDI",
    "g7:QUAY": "QUAY",
    "g7:RESN": "RESN",
    "g7:ROLE": "ROLE",
    "g7:SEX": "SEX",
    "g7:FAMC-STAT": "FAMC-STAT",
    "g7:ord-STAT": "ord-STAT",
    "g7:NAME-TYPE": "NAME-TYPE",
}


@dataclass(frozen=True, slots=True)
class Payload:
    """What a structure's payload must be.

    ``kind`` is ``"none"`` (no payload allowed), ``"Y"`` (``Y`` or nothing), ``"pointer"`` (to
    a record whose tag is ``target``) or ``"value"`` (a data type named by ``datatype``, such
    as ``"Text"``, ``"DateValue"`` or ``"List:Enum"``).
    """

    kind: str
    datatype: str | None = None
    target: str | None = None


@dataclass(frozen=True, slots=True)
class Child:
    uri: str
    required: bool
    singular: bool


@dataclass(slots=True)
class StructureType:
    uri: str
    tag: str
    payload: Payload
    children: dict[str, Child] = field(default_factory=dict)

    @property
    def enum_set(self) -> frozenset[str] | None:
        name = ENUM_SET_OF.get(self.uri)
        return ENUM_SETS[name] if name is not None else None


_LINE_RE = re.compile(r"^(n|0|\+\d+) (.*?) \{([01]):([1M])\}(?: (\S+))?$")


@dataclass(frozen=True, slots=True)
class _GrammarLine:
    offset: int
    body: str
    required: bool
    singular: bool
    uri: str | None


def _parse_rules(text: str) -> dict[str, list[_GrammarLine]]:
    rules: dict[str, list[_GrammarLine]] = {}
    current: list[_GrammarLine] | None = None
    for raw in text.splitlines():
        if raw.endswith(" :="):
            current = rules.setdefault(raw[:-3], [])
            continue
        match = _LINE_RE.match(raw)
        if match is None or current is None:
            raise ValueError(f"unreadable grammar line: {raw!r}")
        level, body, low, high, uri = match.groups()
        offset = 0 if level in ("n", "0") else int(level[1:])
        current.append(_GrammarLine(offset, body, low == "1", high == "1", uri))
    return rules


def _parse_payload(tokens: list[str]) -> Payload:
    if not tokens:
        return Payload("none")
    descriptor = " ".join(tokens)
    if descriptor == "[Y|<NULL>]":
        return Payload("Y")
    if descriptor.startswith("@<XREF:"):
        return Payload("pointer", target=descriptor[len("@<XREF:") : -len(">@")])
    if descriptor.startswith("<") and descriptor.endswith(">"):
        return Payload("value", datatype=descriptor[1:-1])
    raise ValueError(f"unknown payload descriptor {descriptor!r}")


class _Builder:
    def __init__(self, rules: dict[str, list[_GrammarLine]]) -> None:
        self.rules = rules
        self.types: dict[str, StructureType] = {}
        self.records: dict[str, str] = {}
        self.done: set[tuple[str, str | None, bool, bool]] = set()

    def expand(self, rule: str, base: int, parent: str | None, req: bool, sing: bool) -> None:
        # Rules are mutually recursive (a note cites a source whose citation carries notes);
        # expanding a rule twice under the same owner adds nothing, so stop there.
        key = (rule, parent, req, sing)
        if key in self.done:
            return
        self.done.add(key)
        local: dict[int, str] = {}
        for line in self.rules[rule]:
            level = base + line.offset
            owner = parent if line.offset == 0 else local.get(level - 1)
            if line.offset == 0:
                required, singular = req and line.required, sing and line.singular
            else:
                required, singular = line.required, line.singular
            if line.body.startswith("<<"):
                self.expand(line.body[2:-2], level, owner, required, singular)
                continue
            tokens = line.body.split(" ")
            if tokens[0].startswith("@XREF:"):
                tokens = tokens[1:]
            tag, payload = tokens[0], _parse_payload(tokens[1:])
            if line.uri is None:
                raise ValueError(f"structure line without URI: {line.body!r}")
            uri = line.uri
            self.types.setdefault(uri, StructureType(uri, tag, payload))
            if owner is None:
                self.records.setdefault(tag, uri)
            else:
                self.types[owner].children.setdefault(tag, Child(uri, required, singular))
            local[level] = uri


def _build() -> tuple[dict[str, StructureType], dict[str, str]]:
    builder = _Builder(_parse_rules(GRAMMAR))
    builder.expand("HEADER", 0, None, True, True)
    builder.expand("RECORD", 0, None, False, False)
    return builder.types, builder.records


STRUCTURE_TYPES, _RECORDS = _build()
#: Level-0 tags (``HEAD`` included) mapped to their structure-type URI.
RECORD_TYPES: dict[str, str] = dict(_RECORDS)


def child_type(parent_uri: str, tag: str) -> StructureType | None:
    """The structure type a standard ``tag`` has under ``parent_uri``, if the spec permits it."""
    parent = STRUCTURE_TYPES.get(parent_uri)
    if parent is None:
        return None
    child = parent.children.get(tag)
    return STRUCTURE_TYPES[child.uri] if child is not None else None


def record_tag_of(uri: str) -> str | None:
    """The tag of the record type ``uri`` (``g7:record-INDI`` -> ``INDI``)."""
    for tag, record_uri in RECORD_TYPES.items():
        if record_uri == uri:
            return tag
    return None
