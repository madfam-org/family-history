"""GEDCOM 7.0, GEDCOM 5.5.1 and GEDZIP → Tree, with an import report.

The version is read from `HEAD.GEDC.VERS`: 7.x goes to `parse_gedcom7` (tolerant), anything
else to `import_gedcom551`, which upgrades it to the 7.0 model first. A GEDZIP archive yields
its `gedcom.ged`; media entries are skipped with a warning until media storage lands. The
mapping is the inverse of gedcom_out.py; whatever this importer cannot keep is reported as a
warning with its line number.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from family_history.domain.dates import DateParseError, format_date_value, parse_date_value
from family_history.domain.events import EventType, event_type_from_gedcom
from family_history.gedcom import GedzipError, GedzipLimits, import_gedcom551, iter_gedzip, mexico
from family_history.gedcom.model_parts import EVENT_TAGS
from family_history.gedcom.parse7 import parse_gedcom7
from family_history.gedcom.structure import VOID, Structure
from family_history.interchange.gedcom_map import (
    ATTRIBUTE_TYPES,
    KIND_TYPES,
    PRODUCT,
    name_type_from_gedcom,
    pedigree_from_gedcom,
    role_from_gedcom,
    split_particle,
)
from family_history.interchange.tree import (
    FIELD_CAUSE_OF_DEATH,
    FIELD_IDENTITY,
    FIELD_OCCURRED,
    TAssertion,
    TAssociation,
    TCitation,
    TEvent,
    TName,
    TParentLink,
    TParticipant,
    TPerson,
    TPlace,
    Tree,
    TSource,
    TUnion,
)
from family_history.models.enums import ParticipantRole
from family_history.services.privacy import default_sensitivity

MAX_DIAGNOSTICS = 500
PLACE_KINDS = ("pais", "estado", "municipio", "localidad")
_VERSION_RE = re.compile(r"(?m)^\s*1\s+GEDC\b[^\n]*\n(?:\s*[3-9][^\n]*\n)*\s*2\s+VERS\s+(\S+)")
_HEAD_RE = re.compile(r"\s*0\s+HEAD\b")
_INDI_SKIP = frozenset(
    {"NAME", "SEX", "RESN", "FAMC", "FAMS", "SOUR", "NOTE", "SNOTE", "OBJE", "CHAN", "CREA",
     "UID", "EXID", "REFN", "ASSO", "ALIA", "ANCI", "DESI", "SUBM", "NO"}
)  # fmt: skip


#: The job `error_code` for any upload that is not a readable GEDCOM dataset or GEDZIP archive.
INVALID = "gedcom_invalid"


class GedcomImportError(ValueError):
    """The upload is not a GEDCOM dataset this importer can read (`error_code` on the job)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Report:
    """The job report: the GEDCOM engine's `ImportReport` shape."""

    source_version: str = ""
    source_product: str | None = None
    container: str = "gedcom"
    record_counts: dict[str, int] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    truncated: int = 0
    extension_tags: dict[str, int] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, line: int | None = None) -> None:
        if len(self.diagnostics) >= MAX_DIAGNOSTICS:
            self.truncated += 1
            return
        self.diagnostics.append(
            {"severity": severity, "code": code, "message": message, "line": line}
        )

    def warn(self, code: str, message: str, line: int | None = None) -> None:
        self.add("warning", code, message, line)

    @property
    def warnings(self) -> list[dict[str, Any]]:
        return [d for d in self.diagnostics if d["severity"] != "info"]

    def as_dict(self, created: dict[str, int]) -> dict[str, Any]:
        diagnostics = list(self.diagnostics)
        if self.truncated:
            diagnostics.append(
                {
                    "severity": "info",
                    "code": "diagnostics_truncated",
                    "message": f"{self.truncated} more diagnostics were not listed",
                    "line": None,
                }
            )
        return {
            "source_version": self.source_version,
            "source_product": self.source_product,
            "record_counts": dict(sorted(self.record_counts.items())),
            "created_records": dict(sorted(created.items())),
            "diagnostics": diagnostics,
            "extension_tags": dict(sorted(self.extension_tags.items())),
        }


def unpack(data: bytes, report: Report) -> bytes:
    """The GEDCOM bytes of an upload: itself, or `gedcom.ged` from a GEDZIP."""
    if not data.startswith(b"PK\x03\x04"):
        return data
    report.container = "gedzip"
    try:
        entries = iter_gedzip(data, limits=GedzipLimits(max_total_bytes=256 * 1024 * 1024))
        _, gedcom = next(entries)
        for name, _ in entries:
            report.warn("gedzip_media_skipped", f"media file not imported yet: {name[:200]}")
    except (GedzipError, StopIteration) as exc:
        raise GedcomImportError(INVALID, "The GEDZIP archive could not be read.") from exc
    return gedcom


def _prefix_text(data: bytes) -> str:
    head = data[:8192]
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = head.decode("utf-16", errors="replace")
    else:
        text = head.decode("utf-8", errors="replace")
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def detect_version(data: bytes) -> str:
    found = _VERSION_RE.search(_prefix_text(data))
    return found.group(1) if found else ""


def read_roots(data: bytes, report: Report) -> list[Structure]:
    gedcom = unpack(data, report)
    if not _HEAD_RE.match(_prefix_text(gedcom)):
        raise GedcomImportError(INVALID, "The file does not start with a GEDCOM header.")
    version = detect_version(gedcom)
    if version.startswith("7"):
        parsed = parse_gedcom7(gedcom)
        report.source_version = version
        diagnostics = parsed.diagnostics
        report.extension_tags = dict(parsed.extension_tags)
        roots = parsed.structures
        report.record_counts = dict(Counter(r.tag for r in roots if r.tag not in ("HEAD", "TRLR")))
    else:
        imported = import_gedcom551(gedcom)
        report.source_version = imported.report.source_version or version or "5.5.1"
        diagnostics = imported.report.diagnostics
        report.extension_tags = dict(imported.report.extension_tags)
        report.record_counts = dict(imported.report.record_counts)
        roots = imported.structures
    for diagnostic in diagnostics:
        report.add(diagnostic.severity.value, diagnostic.code, diagnostic.message, diagnostic.line)
    head = next((root for root in roots if root.tag == "HEAD"), None)
    if head is None:
        raise GedcomImportError(INVALID, "The file is not a GEDCOM dataset.")
    report.source_product = head.text("SOUR")
    return roots


class _Importer:
    def __init__(self, roots: list[Structure], report: Report) -> None:
        self.roots = roots
        self.report = report
        self.tree = Tree()
        head = next(r for r in roots if r.tag == "HEAD")
        self.ours = (head.text("SOUR") or "") == PRODUCT
        self.people: dict[str, TPerson] = {}
        self.places: dict[tuple[str, ...], str] = {}
        self.sources: dict[str, str] = {}
        self.citations: dict[tuple[Any, ...], str] = {}
        self.pedigrees: dict[tuple[str, str], str] = {}
        self.counter = Counter[str]()

    def _ref(self, prefix: str) -> str:
        self.counter[prefix] += 1
        return f"{prefix}{self.counter[prefix]}"

    def _order(self, prefix: str) -> str:
        return f"{self.counter[prefix]:09d}"

    # -- records ---------------------------------------------------------------------------

    def run(self) -> Tree:
        repos = {r.xref: r.text("NAME") for r in self.roots if r.tag == "REPO" and r.xref}
        for record in self.roots:
            if record.tag == "SOUR" and record.xref:
                self._source(record, repos)
        individuals = [r for r in self.roots if r.tag == "INDI" and r.xref]
        for record in individuals:
            self._person(record)
        for record in individuals:
            self._individual_facts(record)
        for record in self.roots:
            if record.tag == "FAM":
                self._family(record)
            elif record.tag == "OBJE":
                self.report.warn("media_skipped", "media records are not imported yet", record.line)
        return self.tree

    def _source(self, record: Structure, repos: dict[str, str | None]) -> None:
        ref = self._ref("S")
        repo = record.first("REPO")
        repository = repos.get(repo.pointer) if repo is not None and repo.pointer else None
        title = record.text("TITL") or record.text("ABBR") or "Fuente sin título"
        self.tree.sources.append(
            TSource(
                ref, "other", title[:500], (repository or "")[:500] or None, {}, self._order("S")
            )  # fmt: skip
        )
        self.sources[record.xref or ""] = ref

    def _names(self, record: Structure) -> list[TName]:
        names: list[TName] = []
        for node in record.all("NAME"):
            mexican = mexico.name_from_structure(node)
            particle_p, paternal = split_particle(mexican.paternal_surname)
            particle_m, maternal = split_particle(mexican.maternal_surname)
            extras = [
                p.payload
                for p in node.all("SURN")
                if p.payload and p.text("_FH_SURNAME_LINE") == "OTHER"
            ]
            type_node = node.first("TYPE")
            phrase = type_node.text("PHRASE") if type_node is not None else None
            given = (mexican.given or "").strip() or None
            if not (given or paternal or maternal or extras or mexican.nicknames):
                continue
            particles = {k: v for k, v in (("paterno", particle_p), ("materno", particle_m)) if v}
            names.append(
                TName(
                    given=given,
                    apellido_paterno=paternal,
                    apellido_materno=maternal,
                    extra_surnames=extras,
                    particles=particles,
                    nicknames=list(mexican.nicknames),
                    name_type=name_type_from_gedcom(mexican.name_type, phrase),
                    surname_order=(
                        "materno_paterno"
                        if mexican.order is mexico.SurnameOrder.MATERNAL_FIRST
                        else "paterno_materno"
                    ),
                    is_primary=not names,
                )
            )
        if not names:
            self.report.warn("person_without_name", "a person had no readable name", record.line)
            names.append(TName(given="Sin nombre", is_primary=True))
        return names

    def _person(self, record: Structure) -> None:
        ref = self._ref("P")
        sex = record.text("SEX") or "U"
        resn = (record.text("RESN") or "").upper()
        person = TPerson(
            ref,
            sex if sex in ("M", "F", "X", "U") else "U",
            "private" if "PRIVACY" in resn else "space",
            self._names(record),
            order=self._order("P"),
        )
        self.tree.people.append(person)
        self.people[record.xref or ""] = person
        for famc in record.all("FAMC"):
            pedi = famc.first("PEDI")
            pedigree, warning = pedigree_from_gedcom(
                pedi.payload if pedi is not None else None,
                pedi.text("PHRASE") if pedi is not None else None,
            )
            if warning:
                self.report.warn(warning, "pedigree imported as an approximation", famc.line)
            if famc.pointer:
                self.pedigrees[(record.xref or "", famc.pointer)] = pedigree

    def _individual_facts(self, record: Structure) -> None:
        person = self.people[record.xref or ""]
        for node in record.children:
            if node.tag in _INDI_SKIP or node.tag.startswith("_"):
                continue
            if node.tag in EVENT_TAGS:
                self._event(node, [person.ref])
            else:
                self.report.warn("structure_skipped", f"INDI.{node.tag} is not imported", node.line)
        citations = self._citations(record)
        if citations:
            self._assertion("person", person.ref, FIELD_IDENTITY, True, "accepted", citations)

    def _family(self, record: Structure) -> None:
        partners = [
            self.people[p.pointer].ref
            for tag in ("HUSB", "WIFE")
            for p in record.all(tag)
            if p.pointer in self.people
        ]
        partners = list(dict.fromkeys(partners))
        status = "married"
        for node in record.children:
            if node.tag == "EVEN" and mexico.union_kind(node) is mexico.EventKind.FREE_UNION:
                status = "union_libre"
                if node.first("DATE") is not None or node.first("PLAC") is not None:
                    self._event(node, partners, forced=EventType.OTHER)
            elif node.tag == "DIV":
                status = "divorced"
                if any(c.tag not in ("_FH_SENSITIVITY", "RESN") for c in node.children):
                    self._event(node, partners)
            elif node.tag in EVENT_TAGS:
                self._event(node, partners)
        if len(partners) == 2:
            pair = (partners[0], partners[1])
            self.tree.unions.append(TUnion(self._ref("F"), pair, status, self._order("F")))
        for child in record.all("CHIL"):
            if child.pointer not in self.people:
                continue
            kid = self.people[child.pointer].ref
            pedigree = self.pedigrees.get((child.pointer, record.xref or ""), "birth")
            for parent in partners:
                if parent != kid:
                    link = TParentLink(self._ref("R"), parent, kid, pedigree, self._order("R"))
                    self.tree.parent_links.append(link)

    # -- events ----------------------------------------------------------------------------

    def _event_type(self, node: Structure) -> EventType:
        kind = mexico.event_kind(node)
        if kind in KIND_TYPES:
            return KIND_TYPES[kind]
        try:
            return event_type_from_gedcom(node.tag, node.text("TYPE"))
        except ValueError:
            return EventType.OTHER

    def _event(
        self, node: Structure, principals: list[str], forced: EventType | None = None
    ) -> None:
        if not principals:
            self.report.warn("event_without_person", f"{node.tag} has no person", node.line)
            return
        kind = forced or self._event_type(node)
        if kind is EventType.OTHER and node.tag not in ("EVEN",) and forced is None:
            self.report.warn("event_as_other", f"{node.tag} imported as another event", node.line)
        description = self._description(node, kind)
        date_value, date_original = self._date(node)
        event = TEvent(
            self._ref("E"),
            kind.value,
            date_value,
            date_original,
            self._place(node.text("PLAC")),
            description,
            self._sensitivity(node, kind),
            [TParticipant(p, ParticipantRole.PRINCIPAL.value) for p in principals],
            order=self._order("E"),
        )
        for asso in node.all("ASSO"):
            self._association(event, asso)
        self.tree.events.append(event)
        citations = self._citations(node)
        if citations:
            self._assertion("event", event.ref, FIELD_OCCURRED, True, "accepted", citations)
        cause = node.text("CAUS")
        if cause:
            self._assertion("event", event.ref, FIELD_CAUSE_OF_DEATH, cause, "suggested", [],
                            sensitivity="health")  # fmt: skip

    def _description(self, node: Structure, kind: EventType) -> str | None:
        if node.tag == "EVEN" or kind in ATTRIBUTE_TYPES:
            payload = (node.payload or "").strip()
            if payload and payload != kind.label_es:
                return payload
            type_text = node.text("TYPE")
            if kind is EventType.OTHER and type_text and type_text != kind.label_es:
                return type_text
            return None
        note = node.first("NOTE")
        return note.payload if note is not None and note.payload else None

    def _date(self, node: Structure) -> tuple[str | None, str | None]:
        date = node.first("DATE")
        if date is None:
            return None, None
        phrase = date.text("PHRASE")
        payload = (date.payload or "").strip()
        if not payload:
            return None, phrase
        try:
            value = parse_date_value(payload)
        except DateParseError:
            self.report.warn("date_kept_as_text", "a date was kept only as text", date.line)
            return None, phrase or payload
        return format_date_value(value) or None, phrase

    def _place(self, text: str | None) -> str | None:
        if not text or not text.strip():
            return None
        parts = [p.strip() for p in text.split(",")]
        parts = [p for p in parts if p] or [text.strip()]
        path = tuple(reversed(parts))
        parent: str | None = None
        for depth in range(1, len(path) + 1):
            key = path[:depth]
            if key not in self.places:
                ref = self._ref("L")
                kind = PLACE_KINDS[depth - 1] if depth <= len(PLACE_KINDS) else "other"
                place = TPlace(ref, key[-1][:300], kind, parent, order=self._order("L"))
                self.tree.places.append(place)
                self.places[key] = ref
            parent = self.places[key]
        return parent

    def _sensitivity(self, node: Structure, kind: EventType) -> str | None:
        declared = sorted(c.value for c in mexico.sensitivity_of(node))
        if len(declared) > 1:
            self.report.warn("sensitivity_narrowed", "an event kept one sensitivity", node.line)
        if declared:
            return declared[0].lower()
        if self.ours:
            return None
        default = default_sensitivity(kind.value)
        return default.value if default else None

    def _association(self, event: TEvent, asso: Structure) -> None:
        pointer = asso.pointer
        if pointer is None or pointer == VOID or pointer not in self.people:
            self.report.warn("association_skipped", "an ASSO without a person", asso.line)
            return
        role = asso.first("ROLE")
        phrase = (role.text("PHRASE") if role is not None else None) or asso.text("PHRASE")
        kind, value, kept_phrase = role_from_gedcom(role.payload or "" if role else "", phrase)
        person = self.people[pointer].ref
        if kind == "participant":
            if not any(p.person == person and p.role == value for p in event.participants):
                event.participants.append(TParticipant(person, value))
        elif not any(a.person == person and a.role == value for a in event.associations) and all(
            p.person != person for p in event.participants if p.role == "principal"
        ):
            event.associations.append(TAssociation(person, value, kept_phrase))

    def _citations(self, node: Structure) -> list[str]:
        refs: list[str] = []
        for sour in node.all("SOUR"):
            if sour.pointer not in self.sources:
                self.report.warn("citation_skipped", "a citation without a source", sour.line)
                continue
            data = sour.first("DATA")
            quay = sour.text("QUAY")
            key = (
                self.sources[sour.pointer],
                sour.text("PAGE"),
                data.text("TEXT") if data is not None else None,
                int(quay) if quay and quay.isdigit() and int(quay) <= 3 else None,
            )
            if key not in self.citations:
                ref = self._ref("C")
                page = key[1][:100] if key[1] else None
                self.tree.citations.append(
                    TCitation(ref, key[0], page, None, None, key[3], key[2], self._order("C"))
                )
                self.citations[key] = ref
            if self.citations[key] not in refs:
                refs.append(self.citations[key])
        return refs

    def _assertion(
        self,
        subject_type: str,
        subject: str,
        field_name: str,
        value: Any,
        status: str,
        citations: list[str],
        sensitivity: str | None = None,
    ) -> None:
        ref = self._ref("A")
        self.tree.assertions.append(
            TAssertion(
                ref,
                subject_type,
                subject,
                field_name,
                value,
                status,
                sensitivity,
                citations,
                self._order("A"),
            )  # fmt: skip
        )


def tree_from_gedcom(data: bytes) -> tuple[Tree, Report]:
    report = Report()
    roots = read_roots(data, report)
    return _Importer(roots, report).run(), report
