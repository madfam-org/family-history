"""The typed GEDCOM 7.0 document: header, records and the document that holds them.

`GedcomDocument.from_structures` builds the typed view from level-0 `Structure` nodes and
`GedcomDocument.to_structures` turns it back, deterministically. Records whose tag the model
does not know (extension records such as ``_LOC``, or stray standard tags in tolerant mode) are
kept verbatim in ``extension_records``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from family_history.gedcom.model_parts import (
    EVENT_TAGS,
    LDS_TAGS,
    Address,
    Association,
    ChangeDate,
    ChildFamilyLink,
    CreationDate,
    Event,
    ExactDate,
    Identifier,
    MediaFile,
    MediaLink,
    NonEvent,
    Note,
    PersonalName,
    PointerWithPhrase,
    RepositoryCitation,
    SourceCitation,
    SpouseFamilyLink,
    TextValue,
)
from family_history.gedcom.structure import Structure
from family_history.gedcom.typed import (
    Typed,
    many_node,
    many_pointer,
    many_raw,
    many_text,
    one_node,
    one_pointer,
    one_raw,
    one_text,
    payload_text,
    record_xref,
)


@dataclass(kw_only=True)
class Gedc(Typed):
    version: str | None = one_text("VERS")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Schema(Typed):
    """``HEAD.SCHMA``: tag definitions, each ``"_TAG uri"``."""

    tags: list[str] = many_text("TAG")
    other: list[Structure] = field(default_factory=list)

    def definitions(self) -> dict[str, str]:
        """Extension tag -> URI. A tag defined twice keeps its first URI."""
        result: dict[str, str] = {}
        for entry in self.tags:
            tag, _, uri = entry.partition(" ")
            if tag and uri:
                result.setdefault(tag, uri.strip())
        return result


@dataclass(kw_only=True)
class HeaderSource(Typed):
    """``HEAD.SOUR``: the product that wrote the file."""

    value: str | None = payload_text()
    version: str | None = one_text("VERS")
    name: str | None = one_text("NAME")
    corporation: Structure | None = one_raw("CORP")
    data: Structure | None = one_raw("DATA")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class HeaderPlace(Typed):
    form: str | None = one_text("FORM")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Header(Typed):
    gedc: Gedc | None = one_node("GEDC", Gedc)
    schema: Schema | None = one_node("SCHMA", Schema)
    source: HeaderSource | None = one_node("SOUR", HeaderSource)
    destination: str | None = one_text("DEST")
    date: ExactDate | None = one_node("DATE", ExactDate)
    submitter: str | None = one_pointer("SUBM")
    copyright: str | None = one_text("COPR")
    language: str | None = one_text("LANG")
    place: HeaderPlace | None = one_node("PLAC", HeaderPlace)
    note: Note | None = one_node("NOTE", Note)
    shared_note: str | None = one_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)

    @property
    def version(self) -> str | None:
        return self.gedc.version if self.gedc is not None else None

    def extension_definitions(self) -> dict[str, str]:
        return self.schema.definitions() if self.schema is not None else {}


@dataclass(kw_only=True)
class Individual(Typed):
    xref: str | None = record_xref()
    restriction: str | None = one_text("RESN")
    names: list[PersonalName] = many_node("NAME", PersonalName)
    sex: str | None = one_text("SEX")
    events: list[Event] = many_node(EVENT_TAGS, Event)
    non_events: list[NonEvent] = many_node("NO", NonEvent)
    ordinances: list[Structure] = many_raw(LDS_TAGS)
    child_of: list[ChildFamilyLink] = many_node("FAMC", ChildFamilyLink)
    spouse_of: list[SpouseFamilyLink] = many_node("FAMS", SpouseFamilyLink)
    submitters: list[str] = many_pointer("SUBM")
    associations: list[Association] = many_node("ASSO", Association)
    aliases: list[PointerWithPhrase] = many_node("ALIA", PointerWithPhrase)
    ancestor_interest: list[str] = many_pointer("ANCI")
    descendant_interest: list[str] = many_pointer("DESI")
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Family(Typed):
    xref: str | None = record_xref()
    restriction: str | None = one_text("RESN")
    events: list[Event] = many_node(EVENT_TAGS, Event)
    non_events: list[NonEvent] = many_node("NO", NonEvent)
    husband: PointerWithPhrase | None = one_node("HUSB", PointerWithPhrase)
    wife: PointerWithPhrase | None = one_node("WIFE", PointerWithPhrase)
    children: list[PointerWithPhrase] = many_node("CHIL", PointerWithPhrase)
    associations: list[Association] = many_node("ASSO", Association)
    submitters: list[str] = many_pointer("SUBM")
    ordinances: list[Structure] = many_raw("SLGS")
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Source(Typed):
    xref: str | None = record_xref()
    data: Structure | None = one_raw("DATA")
    author: str | None = one_text("AUTH")
    title: str | None = one_text("TITL")
    abbreviation: str | None = one_text("ABBR")
    publication: str | None = one_text("PUBL")
    text: TextValue | None = one_node("TEXT", TextValue)
    repositories: list[RepositoryCitation] = many_node("REPO", RepositoryCitation)
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Repository(Typed):
    xref: str | None = record_xref()
    name: str | None = one_text("NAME")
    address: Address | None = one_node("ADDR", Address)
    phones: list[str] = many_text("PHON")
    emails: list[str] = many_text("EMAIL")
    faxes: list[str] = many_text("FAX")
    websites: list[str] = many_text("WWW")
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Multimedia(Typed):
    xref: str | None = record_xref()
    restriction: str | None = one_text("RESN")
    files: list[MediaFile] = many_node("FILE", MediaFile)
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class SharedNote(Typed):
    xref: str | None = record_xref()
    value: str | None = payload_text()
    mime: str | None = one_text("MIME")
    language: str | None = one_text("LANG")
    translations: list[TextValue] = many_node("TRAN", TextValue)
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Submitter(Typed):
    xref: str | None = record_xref()
    name: str | None = one_text("NAME")
    address: Address | None = one_node("ADDR", Address)
    phones: list[str] = many_text("PHON")
    emails: list[str] = many_text("EMAIL")
    faxes: list[str] = many_text("FAX")
    websites: list[str] = many_text("WWW")
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    languages: list[str] = many_text("LANG")
    reference_numbers: list[Identifier] = many_node("REFN", Identifier)
    uids: list[str] = many_text("UID")
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    change: ChangeDate | None = one_node("CHAN", ChangeDate)
    creation: CreationDate | None = one_node("CREA", CreationDate)
    other: list[Structure] = field(default_factory=list)


Record = Individual | Family | Source | Repository | Multimedia | SharedNote | Submitter

#: Record classes in the order the writers emit them.
RECORD_CLASSES: tuple[tuple[str, type[Typed]], ...] = (
    ("SUBM", Submitter),
    ("INDI", Individual),
    ("FAM", Family),
    ("SOUR", Source),
    ("REPO", Repository),
    ("OBJE", Multimedia),
    ("SNOTE", SharedNote),
)


@dataclass(kw_only=True)
class GedcomDocument:
    """A whole dataset in the 7.0 shape."""

    header: Header = field(default_factory=Header)
    submitters: list[Submitter] = field(default_factory=list)
    individuals: list[Individual] = field(default_factory=list)
    families: list[Family] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    repositories: list[Repository] = field(default_factory=list)
    media: list[Multimedia] = field(default_factory=list)
    shared_notes: list[SharedNote] = field(default_factory=list)
    extension_records: list[Structure] = field(default_factory=list)

    def records(self) -> Iterator[Record]:
        yield from self.submitters
        yield from self.individuals
        yield from self.families
        yield from self.sources
        yield from self.repositories
        yield from self.media
        yield from self.shared_notes

    def by_xref(self) -> dict[str, Record]:
        """Every typed record that has a cross-reference id, keyed by it."""
        return {r.xref: r for r in self.records() if r.xref is not None}

    def individual(self, xref: str) -> Individual | None:
        return next((i for i in self.individuals if i.xref == xref), None)

    def family(self, xref: str) -> Family | None:
        return next((f for f in self.families if f.xref == xref), None)

    @classmethod
    def from_structures(cls, roots: list[Structure]) -> GedcomDocument:
        """Build the typed document from level-0 structures (``TRLR`` is ignored)."""
        doc = cls()
        lists: dict[str, list[Typed]] = {
            "SUBM": doc.submitters,  # type: ignore[dict-item]
            "INDI": doc.individuals,  # type: ignore[dict-item]
            "FAM": doc.families,  # type: ignore[dict-item]
            "SOUR": doc.sources,  # type: ignore[dict-item]
            "REPO": doc.repositories,  # type: ignore[dict-item]
            "OBJE": doc.media,  # type: ignore[dict-item]
            "SNOTE": doc.shared_notes,  # type: ignore[dict-item]
        }
        classes = dict(RECORD_CLASSES)
        seen_header = False
        for root in roots:
            if root.tag == "HEAD" and not seen_header:
                doc.header = Header.from_structure(root)
                seen_header = True
            elif root.tag == "TRLR":
                continue
            elif root.tag in classes and _record_fits(root):
                lists[root.tag].append(classes[root.tag].from_structure(root))
            else:
                doc.extension_records.append(root)
        return doc

    def to_structures(self) -> list[Structure]:
        """Level-0 structures, ``HEAD`` first and ``TRLR`` last, in a stable order."""
        roots = [self.header.to_structure("HEAD")]
        for tag, _ in RECORD_CLASSES:
            for record in self.records():
                if _tag_of(record) == tag:
                    roots.append(record.to_structure(tag))
        roots.extend(r.copy() for r in self.extension_records)
        roots.append(Structure(tag="TRLR"))
        return roots


def _tag_of(record: Record) -> str:
    for tag, cls in RECORD_CLASSES:
        if isinstance(record, cls):
            return tag
    raise TypeError(f"not a record: {type(record).__name__}")


def _record_fits(root: Structure) -> bool:
    if root.pointer is not None:
        return False
    if root.tag == "SNOTE":
        return True
    return root.payload is None
