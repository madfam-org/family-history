"""Tree → GEDCOM 7.0 (and, through the engine, GEDZIP and GEDCOM 5.5.1).

The mapping (docs/lanes/integration-api.md has the full table):

- INDI: one `NAME` per name form (primary first, `domain`/`gedcom.mexico` surname markers),
  `SEX`, `RESN` (`CONFIDENTIAL` for anyone treated as living, `PRIVACY` for private people),
  the person's events, `FAMC`/`FAMS`, and `SOUR` for citations about the person.
- FAM: one per couple (a union, or two people sharing a family event or a child), or per single
  parent; `HUSB`/`WIFE`, `CHIL` (with `PEDI` on the child's `FAMC`), the couple's events; a
  unión libre is the `EVEN TYPE Unión libre` of `gedcom.mexico`, a divorced couple without a
  divorce event gets `DIV Y`.
- Events: the domain tag and TYPE; `DATE` (canonical value, `PHRASE` = the original text),
  `PLAC` (the place path, leaf first), `NOTE` (description, or the payload of OCCU, EDUC, RESI
  and EVEN), `CAUS`, `ASSO` (padrinos, witnesses, other participants), `SOUR`, and
  `_FH_SENSITIVITY` with `RESN CONFIDENTIAL` when the subject may be living.
- SOUR and REPO records for sources (title and repository name).

Not carried by GEDCOM (the native JSON is lossless): name language, nombre usado, source type
and locator, place kinds and dates of validity, union statuses other than married, unión libre
and divorced, assertion statuses, and assertions other than citations and causes of death.

Xrefs (@I1@, @F1@, @S1@, @R1@) and every list come from a sort of the rendered GEDCOM, never from
database ids, so importing an export and exporting again gives the same bytes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from family_history.domain.events import EventType
from family_history.gedcom import mexico, write_gedcom7, write_gedcom551, write_gedzip
from family_history.gedcom.emit import emit_lines
from family_history.gedcom.model import GedcomDocument
from family_history.gedcom.structure import Structure
from family_history.interchange.canonical import date_key
from family_history.interchange.gedcom_map import (
    ATTRIBUTE_TYPES,
    MEXICO_KINDS,
    PEDIGREE_TO_GEDCOM,
    PRODUCT,
    SURNAME_ORDER_TO_GEDCOM,
    association_role,
    name_type_to_gedcom,
    participant_role,
    place_paths,
)
from family_history.interchange.tree import (
    FIELD_CAUSE_OF_DEATH,
    TCitation,
    TEvent,
    TName,
    TPerson,
    Tree,
)
from family_history.models.enums import AssertionStatus, ParticipantRole, SubjectType
from family_history.services.privacy import treated_as_living

Warning_ = dict[str, Any]


def _render(nodes: Iterable[Structure]) -> str:
    return "\n".join(emit_lines(list(nodes)))


def _sorted_nodes(nodes: Iterable[Structure]) -> list[Structure]:
    unique: dict[str, Structure] = {}
    for node in nodes:
        unique.setdefault(_render([node]), node)
    return [unique[key] for key in sorted(unique)]


def name_structure(name: TName) -> Structure:
    paternal = _with_particle(name.particles.get("paterno"), name.apellido_paterno)
    maternal = _with_particle(name.particles.get("materno"), name.apellido_materno)
    order = SURNAME_ORDER_TO_GEDCOM.get(name.surname_order, mexico.SurnameOrder.PATERNAL_FIRST)
    type_value, phrase = name_type_to_gedcom(name.name_type)
    given = name.given or name.nombre_de_pila
    node = mexico.name_to_structure(
        mexico.MexicanName(
            given=_no_slash(given),
            paternal_surname=_no_slash(paternal),
            maternal_surname=_no_slash(maternal),
            nicknames=tuple(n for n in name.nicknames if n),
            order=order,
            name_type=type_value,
        )
    )
    if phrase:
        type_node = node.first("TYPE")
        if type_node is not None:
            type_node.add("PHRASE", phrase)
    for extra in name.extra_surnames:
        if extra:
            node.add("SURN", _no_slash(extra)).add("_FH_SURNAME_LINE", "OTHER")
    return node


def _with_particle(particle: str | None, surname: str | None) -> str | None:
    if not surname:
        return None
    return f"{particle} {surname}" if particle else surname


def _no_slash(value: str | None) -> str | None:
    return value.replace("/", "-") if value else value


def citation_structure(citation: TCitation, source_xref: str) -> Structure:
    node = Structure(tag="SOUR", pointer=source_xref)
    page = ", ".join(
        part
        for part in (
            citation.page,
            f"foja {citation.foja}" if citation.foja else None,
            f"partida {citation.partida}" if citation.partida else None,
        )
        if part
    )
    if page:
        node.add("PAGE", page)
    if citation.extracted_text:
        node.add("DATA").add("TEXT", citation.extracted_text)
    if citation.quality is not None:
        node.add("QUAY", str(citation.quality))
    return node


@dataclass
class _Family:
    partners: tuple[str, ...]
    children: dict[str, str] = field(default_factory=dict)  # child ref -> pedigree
    events: list[TEvent] = field(default_factory=list)
    status: str | None = None
    xref: str = ""


@dataclass
class _Index:
    """Per-person lookups, so building every INDI stays linear in the tree's size."""

    events: defaultdict[str, list[TEvent]] = field(default_factory=lambda: defaultdict(list))
    as_child: defaultdict[str, list[_Family]] = field(default_factory=lambda: defaultdict(list))
    as_partner: defaultdict[str, list[_Family]] = field(default_factory=lambda: defaultdict(list))


class _Exporter:
    def __init__(self, tree: Tree) -> None:
        self.tree = tree
        self.warnings: list[Warning_] = []
        self.people = {p.ref: p for p in tree.people}
        self.places = place_paths(tree.places)
        self.citations = {c.ref: c for c in tree.citations}
        self.indi: dict[str, str] = {}
        self.sour: dict[str, str] = {}
        self.repo: dict[str, str] = {}
        self.cited: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.causes: dict[str, list[str]] = defaultdict(list)
        for assertion in tree.assertions:
            if assertion.status == AssertionStatus.RETRACTED.value:
                continue
            self.cited[(assertion.subject_type, assertion.subject)].update(assertion.citations)
            if (
                assertion.subject_type == SubjectType.EVENT.value
                and assertion.field == FIELD_CAUSE_OF_DEATH
                and isinstance(assertion.value, str)
                and assertion.value.strip()
            ):
                self.causes[assertion.subject].append(assertion.value.strip())

    # -- xrefs ---------------------------------------------------------------------------

    def _assign(self, items: list[Any], prefix: str, key: Callable[[Any], Any]) -> dict[str, str]:
        ranked = sorted(items, key=lambda item: (key(item), item.order))
        return {item.ref: f"@{prefix}{index + 1}@" for index, item in enumerate(ranked)}

    def _own(self, person: TPerson) -> list[Structure]:
        names = sorted(person.names, key=lambda n: not n.is_primary)
        nodes = [name_structure(n) for n in names]
        nodes.append(Structure(tag="SEX", payload=person.sex))
        resn = []
        if treated_as_living(person.living_status):
            resn.append("CONFIDENTIAL")
        if person.visibility == "private":
            resn.append("PRIVACY")
        if resn:
            nodes.append(Structure(tag="RESN", payload=", ".join(resn)))
        return nodes

    def assign_xrefs(self) -> None:
        self.indi = self._assign(self.tree.people, "I", lambda p: _render(self._own(p)))
        repositories = sorted({s.repository for s in self.tree.sources if s.repository})
        self.repo = {name: f"@R{index + 1}@" for index, name in enumerate(repositories)}
        self.sour = self._assign(self.tree.sources, "S", lambda s: (s.title, s.repository or ""))

    # -- events ----------------------------------------------------------------------------

    def _living(self, refs: Iterable[str]) -> bool:
        return any(
            treated_as_living(self.people[r].living_status) for r in refs if r in self.people
        )

    def event_structure(self, event: TEvent, in_family: bool) -> Structure:
        kind = EventType(event.type)
        mexican = MEXICO_KINDS.get(kind)
        if mexican is not None:
            node = mexico.event_structure(mexican)
        else:
            node = Structure(tag=kind.gedcom_tag)
            if kind.gedcom_tag == "EVEN":
                node.add("TYPE", kind.label_es)
        has_payload = kind.gedcom_tag == "EVEN" or kind in ATTRIBUTE_TYPES
        if has_payload:
            node.payload = event.description or kind.label_es
        if event.date_value or event.date_original:
            date = node.add("DATE", event.date_value)
            if event.date_original:
                date.add("PHRASE", event.date_original)
        if event.place and event.place in self.places:
            node.add("PLAC", self.places[event.place])
        if event.description and not has_payload:
            node.add("NOTE", event.description)
        if not has_payload and node.first("DATE") is None and node.first("PLAC") is None:
            node.payload = "Y"
        causes = sorted(self.causes.get(event.ref, []))
        if causes and kind.is_death_evidence:
            caus = mexico.apply_sensitivity(
                Structure(tag="CAUS", payload=causes[0]),
                {mexico.Sensitivity.HEALTH},
                subject_living=False,
            )
            node.children.append(caus)
        node.children.extend(self._associations(event, in_family))
        node.children.extend(self._citations(SubjectType.EVENT.value, event.ref))
        if event.sensitivity:
            principals = [
                p.person
                for p in event.participants
                if p.role in (ParticipantRole.PRINCIPAL.value, ParticipantRole.SPOUSE.value)
            ]
            node = mexico.apply_sensitivity(
                node,
                {mexico.Sensitivity(event.sensitivity.upper())},
                subject_living=self._living(principals),
            )
        return node

    def _associations(self, event: TEvent, in_family: bool) -> list[Structure]:
        nodes: list[Structure] = []
        for part in event.participants:
            if part.role == ParticipantRole.PRINCIPAL.value:
                continue
            if part.role == ParticipantRole.SPOUSE.value and in_family:
                continue
            role, phrase = participant_role(part.role)
            nodes.append(self._asso(part.person, role, phrase))
        for assoc in event.associations:
            role, phrase = association_role(assoc.role, assoc.phrase)
            nodes.append(self._asso(assoc.person, role, phrase))
        return _sorted_nodes(nodes)

    def _asso(self, person: str, role: str, phrase: str | None) -> Structure:
        node = Structure(tag="ASSO", pointer=self.indi[person])
        role_node = node.add("ROLE", role)
        if phrase:
            role_node.add("PHRASE", phrase)
        return node

    def _citations(self, subject_type: str, ref: str) -> list[Structure]:
        nodes = [
            citation_structure(self.citations[c], self.sour[self.citations[c].source])
            for c in self.cited.get((subject_type, ref), set())
            if c in self.citations
        ]
        return _sorted_nodes(nodes)

    def _sorted_events(self, items: list[tuple[TEvent, Structure]]) -> list[Structure]:
        keyed = sorted(items, key=lambda pair: (date_key(pair[0].date_value), _render([pair[1]])))
        return [node for _, node in keyed]

    # -- families --------------------------------------------------------------------------

    def _number(self, ref: str) -> int:
        return int(self.indi[ref].strip("@")[1:])

    def families(self) -> dict[frozenset[str], _Family]:
        units: dict[frozenset[str], _Family] = {}

        def unit(partners: Iterable[str]) -> _Family:
            ordered = tuple(sorted(set(partners), key=self._number))
            key = frozenset(ordered)
            if key not in units:
                units[key] = _Family(partners=ordered)
            return units[key]

        for union in self.tree.unions:
            unit(union.partners).status = union.status
        by_child: dict[tuple[str, str], list[str]] = defaultdict(list)
        for link in self.tree.parent_links:
            by_child[(link.child, link.pedigree)].append(link.parent)
        for (child, pedigree), parents in by_child.items():
            groups = [parents] if len(set(parents)) <= 2 else [[p] for p in parents]
            for group in groups:
                unit(group).children[child] = pedigree
        for event in self.tree.events:
            if not EventType(event.type).is_family_event:
                continue
            couple = sorted(
                {
                    p.person
                    for p in event.participants
                    if p.role in (ParticipantRole.PRINCIPAL.value, ParticipantRole.SPOUSE.value)
                },
                key=self._number,
            )
            if not couple:
                self.warnings.append({"code": "event_without_principal", "message": event.type})
                continue
            if len(couple) > 2:
                self.warnings.append({"code": "family_event_over_two", "message": event.type})
            unit(couple[:2]).events.append(event)
        ranked = sorted(units.values(), key=lambda f: [self._number(p) for p in f.partners])
        for index, family in enumerate(ranked):
            family.xref = f"@F{index + 1}@"
        return units

    def family_record(self, family: _Family) -> Structure:
        node = Structure(tag="FAM", xref=family.xref)
        husband, wife = _spouses(family.partners, self.people)
        if husband:
            node.add("HUSB", pointer=self.indi[husband])
        if wife:
            node.add("WIFE", pointer=self.indi[wife])
        for child in sorted(family.children, key=self._number):
            node.add("CHIL", pointer=self.indi[child])
        events = [(e, self.event_structure(e, in_family=True)) for e in family.events]
        node.children.extend(self._sorted_events(events))
        if family.status == "union_libre":
            free = mexico.event_structure(mexico.EventKind.FREE_UNION)
            free.payload = mexico.KIND_LABELS[mexico.EventKind.FREE_UNION]
            node.children.append(free)
        has_divorce = any(e.type == EventType.DIVORCE.value for e in family.events)
        if family.status == "divorced" and not has_divorce:
            node.add("DIV", "Y")
        return node

    # -- records ---------------------------------------------------------------------------

    def individual(self, person: TPerson, index: _Index) -> Structure:
        node = Structure(tag="INDI", xref=self.indi[person.ref])
        node.children.extend(self._own(person))
        own_events = [
            (event, self.event_structure(event, in_family=False))
            for event in index.events.get(person.ref, [])
        ]
        node.children.extend(self._sorted_events(own_events))
        as_child = index.as_child.get(person.ref, [])
        for family in as_child:
            famc = node.add("FAMC", pointer=family.xref)
            pedigree = PEDIGREE_TO_GEDCOM.get(family.children[person.ref])
            if pedigree is not None:
                pedi = famc.add("PEDI", pedigree[0])
                if pedigree[1]:
                    pedi.add("PHRASE", pedigree[1])
        for family in index.as_partner.get(person.ref, []):
            node.add("FAMS", pointer=family.xref)
        node.children.extend(self._citations(SubjectType.PERSON.value, person.ref))
        return node

    def document(self) -> GedcomDocument:
        self.assign_xrefs()
        for event in self.tree.events:
            principals = [
                p for p in event.participants if p.role == ParticipantRole.PRINCIPAL.value
            ]
            if not principals and not EventType(event.type).is_family_event:
                self.warnings.append({"code": "event_without_principal", "message": event.type})
        families = self.families()
        head = Structure(tag="HEAD")
        head.add("GEDC").add("VERS", "7.0")
        head.add("SOUR", PRODUCT).add("NAME", "family-history")
        roots = [head]
        people = sorted(self.tree.people, key=lambda p: self._number(p.ref))
        ranked = sorted(families.values(), key=lambda f: int(f.xref.strip("@")[1:]))
        index = _Index()
        for event in self.tree.events:
            if EventType(event.type).is_family_event:
                continue
            for ref in dict.fromkeys(
                p.person for p in event.participants if p.role == ParticipantRole.PRINCIPAL.value
            ):
                index.events[ref].append(event)
        for family in ranked:
            for child in family.children:
                index.as_child[child].append(family)
            for partner in family.partners:
                index.as_partner[partner].append(family)
        roots.extend(self.individual(p, index) for p in people)
        roots.extend(self.family_record(f) for f in ranked)
        for source in sorted(self.tree.sources, key=lambda s: int(self.sour[s.ref][2:-1])):
            record = Structure(tag="SOUR", xref=self.sour[source.ref])
            record.add("TITL", source.title)
            if source.repository:
                record.add("REPO", pointer=self.repo[source.repository])
            roots.append(record)
        for name, xref in sorted(self.repo.items(), key=lambda item: int(item[1][2:-1])):
            roots.append(Structure(tag="REPO", xref=xref, children=[Structure("NAME", name)]))
        return GedcomDocument.from_structures(roots)


def _spouses(
    partners: tuple[str, ...], people: dict[str, TPerson]
) -> tuple[str | None, str | None]:
    if len(partners) == 1:
        only = partners[0]
        return (None, only) if people[only].sex == "F" else (only, None)
    first, second = partners[0], partners[1]
    if people[first].sex == "F" and people[second].sex != "F":
        return second, first
    return first, second


@dataclass
class GedcomExport:
    data: bytes
    warnings: list[Warning_]


def export_gedcom7(tree: Tree) -> GedcomExport:
    exporter = _Exporter(tree)
    document = exporter.document()
    return GedcomExport(write_gedcom7(document), exporter.warnings)


def export_gedzip(tree: Tree) -> GedcomExport:
    exported = export_gedcom7(tree)
    return GedcomExport(write_gedzip(exported.data, {}), exported.warnings)


def export_gedcom551(tree: Tree) -> GedcomExport:
    exporter = _Exporter(tree)
    document = exporter.document()
    result = write_gedcom551(document)
    warnings = exporter.warnings + [
        {"code": d.code, "message": d.message, "line": d.line} for d in result.report
    ]
    return GedcomExport(result.data, warnings)
