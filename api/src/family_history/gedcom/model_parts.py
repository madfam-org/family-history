"""Typed GEDCOM 7.0 substructures: names, events, places, citations and the like.

Each class mirrors one structure of the specification. Field names are English words; the
GEDCOM tag each field maps to is given in its declaration. Anything a class does not model,
including every extension substructure, is kept in its ``other`` list (see
`family_history.gedcom.typed`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from family_history.gedcom.spec import (
    FAMILY_ATTRIBUTES,
    FAMILY_EVENTS,
    INDIVIDUAL_ATTRIBUTES,
    INDIVIDUAL_EVENTS,
)
from family_history.gedcom.structure import Structure
from family_history.gedcom.typed import (
    Typed,
    many_node,
    many_pointer,
    many_raw,
    many_text,
    one_node,
    one_text,
    payload_pointer,
    payload_text,
    tag_name,
)

#: Every tag modelled by `Event`: individual and family events and attributes, plus ``EVEN``.
EVENT_TAGS = INDIVIDUAL_EVENTS | FAMILY_EVENTS | INDIVIDUAL_ATTRIBUTES | FAMILY_ATTRIBUTES | {
    "EVEN"
}
LDS_TAGS = frozenset({"BAPL", "CONL", "ENDL", "INIL", "SLGC", "SLGS"})


@dataclass(kw_only=True)
class Phrased(Typed):
    """An enumeration or short value with an optional free-text ``PHRASE``.

    Used for ``ROLE``, ``PEDI``, ``STAT``, ``NAME.TYPE``, ``MEDI``, ``AGE`` and ``FAMC.ADOP``.
    """

    value: str | None = payload_text()
    phrase: str | None = one_text("PHRASE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Date(Typed):
    """A ``DATE`` (or ``SDATE``) structure. ``value`` is kept as the original string."""

    value: str | None = payload_text()
    time: str | None = one_text("TIME")
    phrase: str | None = one_text("PHRASE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class ExactDate(Typed):
    """A ``DateExact`` ``DATE`` with optional ``TIME`` (``CHAN``, ``CREA``, ``HEAD.DATE``)."""

    value: str | None = payload_text()
    time: str | None = one_text("TIME")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class TextValue(Typed):
    """Text with optional media type and language (``TEXT``, ``NOTE.TRAN``, ``SNOTE.TRAN``)."""

    value: str | None = payload_text()
    mime: str | None = one_text("MIME")
    language: str | None = one_text("LANG")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Identifier(Typed):
    """``REFN`` or ``EXID`` with its optional ``TYPE``."""

    value: str | None = payload_text()
    type: str | None = one_text("TYPE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Crop(Typed):
    top: str | None = one_text("TOP")
    left: str | None = one_text("LEFT")
    height: str | None = one_text("HEIGHT")
    width: str | None = one_text("WIDTH")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class MediaLink(Typed):
    """``OBJE`` pointer to a multimedia record, with optional crop and title."""

    pointer: str | None = payload_pointer()
    crop: Crop | None = one_node("CROP", Crop)
    title: str | None = one_text("TITL")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class CitationData(Typed):
    date: Date | None = one_node("DATE", Date)
    texts: list[TextValue] = many_node("TEXT", TextValue)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class CitationEvent(Typed):
    value: str | None = payload_text()
    phrase: str | None = one_text("PHRASE")
    role: Phrased | None = one_node("ROLE", Phrased)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Note(Typed):
    """An inline ``NOTE``. Its source citations stay generic structures."""

    value: str | None = payload_text()
    mime: str | None = one_text("MIME")
    language: str | None = one_text("LANG")
    translations: list[TextValue] = many_node("TRAN", TextValue)
    citations: list[Structure] = many_raw("SOUR")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class SourceCitation(Typed):
    """``SOUR`` pointer with page, data, event, quality, media and notes."""

    pointer: str | None = payload_pointer()
    page: str | None = one_text("PAGE")
    data: CitationData | None = one_node("DATA", CitationData)
    event: CitationEvent | None = one_node("EVEN", CitationEvent)
    quality: str | None = one_text("QUAY")
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Association(Typed):
    """``ASSO``: a pointer to another individual and the ``ROLE`` they played."""

    pointer: str | None = payload_pointer()
    phrase: str | None = one_text("PHRASE")
    role: Phrased | None = one_node("ROLE", Phrased)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class PlaceTranslation(Typed):
    value: str | None = payload_text()
    language: str | None = one_text("LANG")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class MapCoordinates(Typed):
    latitude: str | None = one_text("LATI")
    longitude: str | None = one_text("LONG")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Place(Typed):
    """``PLAC``: a comma-separated jurisdiction list, most specific first."""

    value: str | None = payload_text()
    form: str | None = one_text("FORM")
    language: str | None = one_text("LANG")
    translations: list[PlaceTranslation] = many_node("TRAN", PlaceTranslation)
    map: MapCoordinates | None = one_node("MAP", MapCoordinates)
    external_ids: list[Identifier] = many_node("EXID", Identifier)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Address(Typed):
    value: str | None = payload_text()
    line1: str | None = one_text("ADR1")
    line2: str | None = one_text("ADR2")
    line3: str | None = one_text("ADR3")
    city: str | None = one_text("CITY")
    state: str | None = one_text("STAE")
    postal_code: str | None = one_text("POST")
    country: str | None = one_text("CTRY")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class PartnerDetail(Typed):
    """``HUSB``/``WIFE`` inside a family event: the partner's age at the event."""

    age: Phrased | None = one_node("AGE", Phrased)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class EventFamilyLink(Typed):
    """``FAMC`` under ``BIRT``, ``CHR`` or ``ADOP``; ``adoption`` is ``FAMC.ADOP``."""

    pointer: str | None = payload_pointer()
    adoption: Phrased | None = one_node("ADOP", Phrased)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class Event(Typed):
    """Any individual or family event or attribute (``BIRT``, ``MARR``, ``OCCU``, ``EVEN``...).

    ``value`` is ``"Y"`` or empty for events and the attribute text for attributes.
    """

    tag: str = tag_name()
    value: str | None = payload_text()
    type: str | None = one_text("TYPE")
    husband: PartnerDetail | None = one_node("HUSB", PartnerDetail)
    wife: PartnerDetail | None = one_node("WIFE", PartnerDetail)
    date: Date | None = one_node("DATE", Date)
    place: Place | None = one_node("PLAC", Place)
    address: Address | None = one_node("ADDR", Address)
    phones: list[str] = many_text("PHON")
    emails: list[str] = many_text("EMAIL")
    faxes: list[str] = many_text("FAX")
    websites: list[str] = many_text("WWW")
    agency: str | None = one_text("AGNC")
    religion: str | None = one_text("RELI")
    cause: str | None = one_text("CAUS")
    restriction: str | None = one_text("RESN")
    sort_date: Date | None = one_node("SDATE", Date)
    age: Phrased | None = one_node("AGE", Phrased)
    family: EventFamilyLink | None = one_node("FAMC", EventFamilyLink)
    associations: list[Association] = many_node("ASSO", Association)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    media: list[MediaLink] = many_node("OBJE", MediaLink)
    uids: list[str] = many_text("UID")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class NonEvent(Typed):
    """``NO``: an event that did not happen, optionally within a ``DATE`` period."""

    value: str | None = payload_text()
    date: Date | None = one_node("DATE", Date)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class NamePiece(Typed):
    """One name piece (``GIVN``, ``SURN``...). A class, not a string, so extension
    substructures under a piece (such as ``_FH_SURNAME_LINE``) keep their place."""

    value: str | None = payload_text()
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class NameTranslation(Typed):
    value: str | None = payload_text()
    language: str | None = one_text("LANG")
    prefixes: list[NamePiece] = many_node("NPFX", NamePiece)
    given: list[NamePiece] = many_node("GIVN", NamePiece)
    nicknames: list[NamePiece] = many_node("NICK", NamePiece)
    surname_prefixes: list[NamePiece] = many_node("SPFX", NamePiece)
    surnames: list[NamePiece] = many_node("SURN", NamePiece)
    suffixes: list[NamePiece] = many_node("NSFX", NamePiece)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class PersonalName(Typed):
    """``NAME``: the full name with the surname between slashes, plus optional pieces."""

    value: str | None = payload_text()
    type: Phrased | None = one_node("TYPE", Phrased)
    prefixes: list[NamePiece] = many_node("NPFX", NamePiece)
    given: list[NamePiece] = many_node("GIVN", NamePiece)
    nicknames: list[NamePiece] = many_node("NICK", NamePiece)
    surname_prefixes: list[NamePiece] = many_node("SPFX", NamePiece)
    surnames: list[NamePiece] = many_node("SURN", NamePiece)
    suffixes: list[NamePiece] = many_node("NSFX", NamePiece)
    translations: list[NameTranslation] = many_node("TRAN", NameTranslation)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    citations: list[SourceCitation] = many_node("SOUR", SourceCitation)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class ChildFamilyLink(Typed):
    """``INDI.FAMC``: the family this individual is a child in, with pedigree and status."""

    pointer: str | None = payload_pointer()
    pedigree: Phrased | None = one_node("PEDI", Phrased)
    status: Phrased | None = one_node("STAT", Phrased)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class SpouseFamilyLink(Typed):
    """``INDI.FAMS``: a family this individual is a partner in."""

    pointer: str | None = payload_pointer()
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class PointerWithPhrase(Typed):
    """``HUSB``, ``WIFE``, ``CHIL`` or ``ALIA``: a pointer with an optional ``PHRASE``."""

    pointer: str | None = payload_pointer()
    phrase: str | None = one_text("PHRASE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class ChangeDate(Typed):
    date: ExactDate | None = one_node("DATE", ExactDate)
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class CreationDate(Typed):
    date: ExactDate | None = one_node("DATE", ExactDate)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class RepositoryCitation(Typed):
    """``SOUR.REPO``: where a source can be found; call numbers stay generic."""

    pointer: str | None = payload_pointer()
    notes: list[Note] = many_node("NOTE", Note)
    shared_notes: list[str] = many_pointer("SNOTE")
    call_numbers: list[Structure] = many_raw("CALN")
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class MediaForm(Typed):
    value: str | None = payload_text()
    medium: Phrased | None = one_node("MEDI", Phrased)
    other: list[Structure] = field(default_factory=list)


@dataclass(kw_only=True)
class MediaFile(Typed):
    """``OBJE.FILE``: a file path (URL) with its media type and optional title."""

    value: str | None = payload_text()
    form: MediaForm | None = one_node("FORM", MediaForm)
    title: str | None = one_text("TITL")
    translations: list[Structure] = many_raw("TRAN")
    other: list[Structure] = field(default_factory=list)
