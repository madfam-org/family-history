"""Upgrade GEDCOM 5.5.1 structure trees to the GEDCOM 7.0 shape.

The upgrader rewrites the generic `Structure` tree in place, then hands it to the 7.0 typed
model. Every change that could alter meaning is reported; pure spelling changes are reported
at info level. Vendor extension tags (``_APID``, ``_UPD``, ``_MARNM``, ``_UID``...) and their
whole subtrees are kept exactly as they were.

The rules, in short (docs/GEDCOM.md has the full table):

* ``HEAD``: ``GEDC.VERS`` -> ``7.0``; ``GEDC.FORM``, ``CHAR``, ``FILE`` and ``SUBN`` removed;
  language names -> BCP 47;
* ``NOTE`` records -> ``SNOTE`` records and ``NOTE @X@`` -> ``SNOTE @X@``; ``SUBN`` records
  removed with a warning;
* cross-reference ids are normalized to the 7.0 grammar (upper case, ``_`` for other
  characters) and every pointer follows;
* inline sources (``SOUR text``) and inline media (``OBJE`` + ``FILE``) become new records;
* dates (see `family_history.gedcom.dates551`), ages, ``SEX``, ``RESN``, ``PEDI``, ``STAT``,
  ``NAME.TYPE``, ``MEDI`` and ``FAMC.ADOP`` values are mapped to 7.0 enumerations, unknown
  values become ``OTHER`` with a ``PHRASE`` keeping the original;
* ``ASSO.RELA`` -> ``ASSO.ROLE`` (``GODP``, ``WITN``... or ``OTHER``) with a ``PHRASE``;
* ``AFN``, ``RFN`` and ``RIN`` -> ``EXID`` with the registered TYPE URIs;
* ``OBJE``/``FILE``/``FORM`` -> ``FILE`` URL + media type + ``MEDI``.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from family_history.gedcom.datatypes import AGE_RE
from family_history.gedcom.dates551 import upgrade_date
from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.spec import ENUM_SETS, FAMILY_EVENTS, INDIVIDUAL_EVENTS
from family_history.gedcom.structure import Structure, is_xref
from family_history.gedcom.upgrade551_media import medium_value, upgrade_media_record
from family_history.gedcom.upgrade551_tables import (
    AGE_KEYWORDS,
    EXID_TYPES,
    LANGUAGES,
    NAME_TYPE_WORDS,
    PEDIGREE_WORDS,
    ROLE_WORDS,
)

_EVENTS = INDIVIDUAL_EVENTS | FAMILY_EVENTS
_XREF_BAD_RE = re.compile(r"[^A-Z0-9_]")
_SEX_WORDS = {
    "M": "M", "F": "F", "U": "U", "X": "X", "MALE": "M", "FEMALE": "F", "UNKNOWN": "U",
    "H": "M", "HOMBRE": "M", "MUJER": "F", "MASCULINO": "M", "FEMENINO": "F",
}
# Keep values that already look like BCP 47 (2-3 letter primary subtag); 5.5.1 language
# names such as "Klingon" do not, and become "und".
_BCP47_SHORT_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*$")
_COORD_RE = re.compile(r"^([NSEW]?)\s*(-?)(\d+(?:\.\d+)?)$")


class Upgrader:
    """One-shot 5.5.1 -> 7.0 tree rewriter."""

    def __init__(self, diagnostics: Diagnostics) -> None:
        self.d = diagnostics
        self.renamed: dict[str, str] = {}
        self.taken: set[str] = set()
        self.new_records: list[Structure] = []
        self.source_system: str | None = None
        self.counter = 0

    def run(self, roots: list[Structure]) -> list[Structure]:
        self._normalize_xrefs(roots)
        head = next((r for r in roots if r.tag == "HEAD"), None)
        if head is None:
            self.d.warning("missing-head", "no HEAD found; one was created", 1)
            head = Structure(tag="HEAD")
        self.source_system = head.text("SOUR")
        records: list[Structure] = []
        for root in roots:
            if root.tag in ("HEAD", "TRLR"):
                continue
            if root.tag == "SUBN":
                self.d.warning(
                    "subn-dropped", "SUBN (LDS submission) record has no 7.0 equivalent; dropped",
                    root.line,
                )
                continue
            if root.tag == "NOTE":
                root.tag = "SNOTE"
                self.d.info("note-record", "NOTE record became an SNOTE record", root.line)
            if root.tag == "OBJE":
                upgrade_media_record(root, self.d)
            if not root.is_extension:
                self._children(root, root.tag)
            records.append(root)
        self._head(head)
        return [head, *records, *self.new_records, Structure(tag="TRLR")]

    # -- cross-reference ids ------------------------------------------------------------

    def _normalize_xrefs(self, roots: list[Structure]) -> None:
        for root in roots:
            if root.xref is not None and is_xref(root.xref):
                self.taken.add(root.xref)
        for root in roots:
            if root.xref is not None and not is_xref(root.xref):
                new = self._fresh(_XREF_BAD_RE.sub("_", root.xref[1:-1].upper()) or "X")
                self.renamed[root.xref] = new
                root.xref = new
        if self.renamed:
            self.d.warning(
                "xref-renamed",
                f"{len(self.renamed)} cross-reference id(s) rewritten to the 7.0 grammar",
            )
        for root in roots:
            for node in root.walk():
                if node.pointer is not None and node.pointer in self.renamed:
                    node.pointer = self.renamed[node.pointer]
                elif node.pointer is not None and not is_xref(node.pointer):
                    node.pointer = "@" + (_XREF_BAD_RE.sub("_", node.pointer[1:-1].upper())) + "@"

    def _fresh(self, base: str) -> str:
        candidate = f"@{base}@"
        suffix = 2
        while candidate in self.taken or candidate == "@VOID@":
            candidate = f"@{base}_{suffix}@"
            suffix += 1
        self.taken.add(candidate)
        return candidate

    # -- header ---------------------------------------------------------------------------

    def _head(self, head: Structure) -> None:
        kept: list[Structure] = []
        for child in head.children:
            if child.tag in ("CHAR", "FILE", "SUBN"):
                self.d.info(
                    "head-dropped", f"HEAD.{child.tag} {child.payload or child.pointer or ''} "
                    "has no 7.0 equivalent; dropped", child.line,
                )
                continue
            if child.tag == "GEDC":
                child.children = [Structure(tag="VERS", payload="7.0", line=child.line)]
            elif child.tag == "LANG":
                self._language(child)
            elif child.tag == "DATE":
                self._date(child)
            kept.append(child)
        if head.first("GEDC") is None:
            kept.insert(0, Structure(tag="GEDC", children=[Structure(tag="VERS", payload="7.0")]))
        head.children = kept

    # -- generic tree walk ----------------------------------------------------------------

    def _children(self, node: Structure, record_tag: str) -> None:
        index = 0
        while index < len(node.children):
            child = node.children[index]
            replacement = self._fix(child, node, record_tag)
            if replacement is None:
                del node.children[index]
                continue
            node.children[index] = replacement
            if not replacement.is_extension:
                self._children(replacement, record_tag)
            index += 1

    def _fix(self, node: Structure, parent: Structure, record_tag: str) -> Structure | None:
        if node.is_extension:
            return node
        tag = node.tag
        if tag == "NOTE" and node.pointer is not None:
            node.tag = "SNOTE"
        elif tag == "SOUR" and node.pointer is None and node.payload is not None:
            self._inline_source(node)
        elif tag == "OBJE" and node.pointer is None:
            self._inline_media(node)
        elif tag in ("DATE", "SDATE"):
            self._date(node)
        elif tag == "AGE":
            self._age(node)
        elif tag == "SEX":
            self._sex(node)
        elif tag == "RESN":
            node.payload = (node.payload or "").upper() or None
        elif tag == "TYPE" and parent.tag == "NAME":
            self._enum(node, NAME_TYPE_WORDS, "NAME-TYPE")
        elif tag == "PEDI":
            self._enum(node, PEDIGREE_WORDS, "PEDI")
        elif tag == "STAT" and parent.tag == "FAMC":
            node.payload = (node.payload or "").upper() or None
        elif tag == "ADOP" and parent.tag == "FAMC":
            node.payload = (node.payload or "").upper() or None
        elif tag == "MEDI":
            medium_value(node, self.d)
        elif tag == "ROLE":
            self._role(node, node.payload or "")
        elif tag == "ASSO":
            self._association(node)
        elif tag in EXID_TYPES:
            self._exid(node)
        elif tag == "LANG":
            self._language(node)
        elif tag == "EMAI":
            node.tag = "EMAIL"
        elif tag in ("LATI", "LONG"):
            self._coordinate(node)
        elif tag == "ALIA" and node.pointer is None and parent.tag == "INDI":
            return self._alias_name(node)
        elif parent.tag in ("INDI", "FAM"):
            self._event_shape(node)
        return node

    # -- individual rules -----------------------------------------------------------------

    def _date(self, node: Structure) -> None:
        if node.payload is None:
            return
        result = upgrade_date(node.payload)
        if result.note is not None:
            message = f"DATE {node.payload!r}: {result.note}"
            if result.interpretive:
                self.d.warning("date-upgraded", message, node.line)
            else:
                self.d.info("date-normalized", message, node.line)
        node.payload = result.value or None
        if result.phrase and node.first("PHRASE") is None:
            node.children.append(Structure(tag="PHRASE", payload=result.phrase, line=node.line))

    def _age(self, node: Structure) -> None:
        original = (node.payload or "").strip()
        upper = original.upper()
        if upper in AGE_KEYWORDS:
            node.payload, phrase = AGE_KEYWORDS[upper]
            node.children.append(Structure(tag="PHRASE", payload=phrase, line=node.line))
            self.d.info("age-keyword", f"AGE {original} written as {node.payload}", node.line)
            return
        candidate = re.sub(r"^([<>])\s*", r"\1 ", original.lower())
        candidate = re.sub(r"(\d+)\s*([ymwd])", r"\1\2", candidate)
        if candidate.isdigit():
            candidate += "y"
        if candidate and AGE_RE.match(candidate):
            if candidate != original:
                self.d.info("age-normalized", f"AGE {original!r} -> {candidate!r}", node.line)
            node.payload = candidate
            return
        if original:
            node.payload = None
            node.children.append(Structure(tag="PHRASE", payload=original, line=node.line))
            self.d.warning("age-phrase", f"AGE {original!r} kept as PHRASE", node.line)

    def _sex(self, node: Structure) -> None:
        original = (node.payload or "").strip()
        mapped = _SEX_WORDS.get(original.upper())
        if mapped is not None:
            node.payload = mapped
            if mapped != original:
                self.d.info("sex-normalized", f"SEX {original!r} -> {mapped}", node.line)
            return
        node.payload = "U"
        self.d.warning("sex-unknown", f"SEX {original!r} is not a 5.5.1 value; set to U", node.line)

    def _enum(self, node: Structure, words: dict[str, str], enum_set: str) -> None:
        original = (node.payload or "").strip()
        if original in ENUM_SETS[enum_set]:
            return
        mapped = words.get(original.lower())
        if mapped is not None and mapped.lower() == original.lower():
            node.payload = mapped
            return
        node.payload = mapped or "OTHER"
        if original:
            node.children.insert(0, Structure(tag="PHRASE", payload=original, line=node.line))
            self.d.warning(
                "enum-mapped", f"{node.tag} {original!r} -> {node.payload} + PHRASE", node.line
            )

    def _role(self, node: Structure, original: str) -> None:
        text = original.strip()
        bare = text.strip("()").strip()
        if bare.upper() in ENUM_SETS["ROLE"]:
            node.payload = bare.upper()
            return
        words = bare.lower().split()
        node.payload = ROLE_WORDS.get(bare.lower()) or (
            ROLE_WORDS.get(words[0], "OTHER") if words else "OTHER"
        )
        if bare:
            node.children.insert(0, Structure(tag="PHRASE", payload=bare, line=node.line))
        self.d.info("role-mapped", f"role {text!r} -> {node.payload} + PHRASE", node.line)

    def _association(self, node: Structure) -> None:
        rela = node.first("RELA")
        kept = [c for c in node.children if c.tag not in ("RELA", "TYPE")]
        dropped_type = node.first("TYPE")
        if dropped_type is not None and (dropped_type.payload or "").upper() != "INDI":
            kept.append(dropped_type)
        if node.first("ROLE") is None:
            role = Structure(tag="ROLE", line=node.line)
            if rela is not None:
                self._role(role, rela.payload or "")
            else:
                role.payload = "OTHER"
                self.d.warning("asso-no-role", "ASSO without RELA got ROLE OTHER", node.line)
            kept.insert(0, role)
        node.children = kept

    def _exid(self, node: Structure) -> None:
        original_tag, value = node.tag, (node.payload or "").strip()
        uri = EXID_TYPES[original_tag]
        if original_tag == "RFN" and ":" in value:
            resource, _, value = value.partition(":")
            uri = f"{uri}#{quote(resource, safe='')}"
        elif original_tag == "RIN" and self.source_system:
            uri = f"{uri}#{quote(self.source_system, safe='')}"
        node.tag = "EXID"
        node.payload = value or None
        node.children = [Structure(tag="TYPE", payload=uri, line=node.line), *node.children]
        self.d.info("exid", f"{original_tag} {value!r} became EXID with TYPE {uri}", node.line)

    def _language(self, node: Structure) -> None:
        original = (node.payload or "").strip()
        mapped = LANGUAGES.get(original.upper())
        if mapped is not None:
            node.payload = mapped
        elif not _BCP47_SHORT_RE.match(original):
            node.payload = "und"
            self.d.warning("language-unknown", f"language {original!r} written as und", node.line)

    def _coordinate(self, node: Structure) -> None:
        original = (node.payload or "").strip()
        match = _COORD_RE.match(original.upper().replace(",", "."))
        if match is None:
            self.d.warning("coordinate", f"{node.tag} {original!r} is not a coordinate", node.line)
            return
        hemisphere, sign, number = match.groups()
        if not hemisphere:
            positive, negative = ("N", "S") if node.tag == "LATI" else ("E", "W")
            hemisphere = negative if sign else positive
            self.d.info("coordinate", f"{node.tag} {original!r} -> {hemisphere}{number}", node.line)
        node.payload = f"{hemisphere}{number}"

    def _alias_name(self, node: Structure) -> Structure:
        self.d.warning(
            "alia-text", "ALIA with a name instead of a pointer became NAME with TYPE AKA",
            node.line,
        )
        name = Structure(tag="NAME", payload=node.payload, line=node.line)
        name.children = [Structure(tag="TYPE", payload="AKA", line=node.line), *node.children]
        return name

    def _event_shape(self, node: Structure) -> None:
        if node.tag in _EVENTS and node.payload not in (None, "Y"):
            text = node.payload or ""
            node.payload = "Y"
            node.children.append(Structure(tag="NOTE", payload=text, line=node.line))
            self.d.warning(
                "event-text", f"{node.tag} text {text!r} moved to a NOTE; payload set to Y",
                node.line,
            )
        if node.tag in ("EVEN", "FACT", "IDNO") and node.first("TYPE") is None:
            label = "Unspecified" if node.tag != "EVEN" or not node.payload else node.payload
            node.children.insert(0, Structure(tag="TYPE", payload=label, line=node.line))
            self.d.warning("type-added", f"{node.tag} without TYPE got TYPE {label!r}", node.line)

    def _inline_source(self, node: Structure) -> None:
        xref = self._fresh(f"FHS{self._next()}")
        record = Structure(tag="SOUR", xref=xref, line=node.line)
        record.children.append(Structure(tag="TITL", payload=node.payload, line=node.line))
        texts = node.all("TEXT")
        if texts:
            joined = "\n".join(t.payload or "" for t in texts)
            record.children.append(Structure(tag="TEXT", payload=joined, line=texts[0].line))
        node.children = [c for c in node.children if c.tag != "TEXT"]
        node.payload, node.pointer = None, xref
        self.new_records.append(record)
        self.d.warning(
            "inline-source", f"source text without a SOUR record became record {xref}", node.line
        )

    def _inline_media(self, node: Structure) -> None:
        xref = self._fresh(f"FHO{self._next()}")
        record = Structure(tag="OBJE", xref=xref, line=node.line)
        link_children: list[Structure] = []
        for child in node.children:
            if child.tag in ("FILE", "FORM", "BLOB"):
                record.children.append(child)
            elif child.tag == "TITL":
                record.children.append(child.copy())
                link_children.append(child)
            else:
                link_children.append(child)
        upgrade_media_record(record, self.d)
        self._children(record, "OBJE")
        node.children, node.payload, node.pointer = link_children, None, xref
        self.new_records.append(record)
        self.d.warning(
            "inline-media", f"embedded multimedia link became record {xref}", node.line
        )

    def _next(self) -> int:
        self.counter += 1
        return self.counter
