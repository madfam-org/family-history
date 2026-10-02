"""The event vocabulary: event types, their GEDCOM 7 tags and labels, and association roles.

Civil and religious marriage are distinct events (GEDCOM `MARR` with a `TYPE`), because in
Mexico they are separate acts with separate records, often on different days. Mexico-specific
events without a GEDCOM tag are typed `EVEN`s: «XV años», «Contrato bracero» and «Cruce
fronterizo».
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AssociationRole",
    "EventSpec",
    "EventType",
    "event_spec",
    "event_type_from_gedcom",
    "role_from_gedcom",
]


class EventType(StrEnum):
    """Events a person or a couple can have."""

    BIRTH = "birth"
    BAPTISM = "baptism"
    CHRISTENING = "christening"
    CONFIRMATION = "confirmation"
    FIRST_COMMUNION = "first_communion"
    MARRIAGE = "marriage"
    CIVIL_MARRIAGE = "civil_marriage"
    RELIGIOUS_MARRIAGE = "religious_marriage"
    DIVORCE = "divorce"
    DEATH = "death"
    BURIAL = "burial"
    CREMATION = "cremation"
    EMIGRATION = "emigration"
    IMMIGRATION = "immigration"
    NATURALIZATION = "naturalization"
    RESIDENCE = "residence"
    OCCUPATION = "occupation"
    EDUCATION = "education"
    QUINCEANERA = "quinceanera"
    BRACERO_CONTRACT = "bracero_contract"
    BORDER_CROSSING = "border_crossing"
    OTHER = "other"

    @property
    def spec(self) -> EventSpec:
        return _SPECS[self]

    @property
    def label_es(self) -> str:
        return _SPECS[self].label_es

    @property
    def label_en(self) -> str:
        return _SPECS[self].label_en

    @property
    def gedcom_tag(self) -> str:
        return _SPECS[self].gedcom_tag

    @property
    def gedcom_type(self) -> str | None:
        """The `TYPE` payload written with the tag, or None."""
        return _SPECS[self].gedcom_type

    @property
    def is_sacramental(self) -> bool:
        """True for Catholic sacraments and religious marriage (sensitivity: religion)."""
        return _SPECS[self].sacramental

    @property
    def is_family_event(self) -> bool:
        """True for events of a couple (`FAM` record) rather than of one person."""
        return _SPECS[self].family_event

    @property
    def is_death_evidence(self) -> bool:
        """True for events that, when evidenced, prove a death (death, burial, cremation)."""
        return self in (EventType.DEATH, EventType.BURIAL, EventType.CREMATION)

    @property
    def bounds_birth(self) -> bool:
        """True for events that happen at or soon after birth, so birth is no later."""
        return self in (EventType.BIRTH, EventType.BAPTISM, EventType.CHRISTENING)


@dataclass(frozen=True, slots=True)
class EventSpec:
    """How an `EventType` is labelled and written to GEDCOM 7."""

    gedcom_tag: str
    label_es: str
    label_en: str
    gedcom_type: str | None = None
    sacramental: bool = False
    family_event: bool = False


_SPECS: dict[EventType, EventSpec] = {
    EventType.BIRTH: EventSpec("BIRT", "Nacimiento", "Birth"),
    EventType.BAPTISM: EventSpec("BAPM", "Bautizo", "Baptism", sacramental=True),
    EventType.CHRISTENING: EventSpec("CHR", "Bautizo de infante", "Christening", sacramental=True),
    EventType.CONFIRMATION: EventSpec("CONF", "Confirmación", "Confirmation", sacramental=True),
    EventType.FIRST_COMMUNION: EventSpec(
        "FCOM", "Primera comunión", "First communion", sacramental=True
    ),
    EventType.MARRIAGE: EventSpec("MARR", "Matrimonio", "Marriage", family_event=True),
    EventType.CIVIL_MARRIAGE: EventSpec(
        "MARR", "Matrimonio civil", "Civil marriage", "Matrimonio civil", family_event=True
    ),
    EventType.RELIGIOUS_MARRIAGE: EventSpec(
        "MARR",
        "Matrimonio religioso",
        "Religious marriage",
        "Matrimonio religioso",
        sacramental=True,
        family_event=True,
    ),
    EventType.DIVORCE: EventSpec("DIV", "Divorcio", "Divorce", family_event=True),
    EventType.DEATH: EventSpec("DEAT", "Defunción", "Death"),
    EventType.BURIAL: EventSpec("BURI", "Sepultura", "Burial"),
    EventType.CREMATION: EventSpec("CREM", "Cremación", "Cremation"),
    EventType.EMIGRATION: EventSpec("EMIG", "Emigración", "Emigration"),
    EventType.IMMIGRATION: EventSpec("IMMI", "Inmigración", "Immigration"),
    EventType.NATURALIZATION: EventSpec("NATU", "Naturalización", "Naturalization"),
    EventType.RESIDENCE: EventSpec("RESI", "Residencia", "Residence"),
    EventType.OCCUPATION: EventSpec("OCCU", "Ocupación", "Occupation"),
    EventType.EDUCATION: EventSpec("EDUC", "Estudios", "Education"),
    EventType.QUINCEANERA: EventSpec("EVEN", "XV años", "Quinceañera", "XV años"),
    EventType.BRACERO_CONTRACT: EventSpec(
        "EVEN", "Contrato bracero", "Bracero contract", "Contrato bracero"
    ),
    EventType.BORDER_CROSSING: EventSpec(
        "EVEN", "Cruce fronterizo", "Border crossing", "Cruce fronterizo"
    ),
    EventType.OTHER: EventSpec("EVEN", "Otro evento", "Other event"),
}


def event_spec(event_type: EventType) -> EventSpec:
    """Return the spec of `event_type`."""
    return _SPECS[event_type]


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


# TYPE payloads recognised on import, accent- and case-insensitive.
_TYPE_ALIASES: dict[tuple[str, str], EventType] = {
    ("MARR", "matrimonio civil"): EventType.CIVIL_MARRIAGE,
    ("MARR", "civil"): EventType.CIVIL_MARRIAGE,
    ("MARR", "civil marriage"): EventType.CIVIL_MARRIAGE,
    ("MARR", "matrimonio religioso"): EventType.RELIGIOUS_MARRIAGE,
    ("MARR", "religioso"): EventType.RELIGIOUS_MARRIAGE,
    ("MARR", "religious"): EventType.RELIGIOUS_MARRIAGE,
    ("MARR", "religious marriage"): EventType.RELIGIOUS_MARRIAGE,
    ("MARR", "matrimonio eclesiastico"): EventType.RELIGIOUS_MARRIAGE,
    ("EVEN", "xv anos"): EventType.QUINCEANERA,
    ("EVEN", "quince anos"): EventType.QUINCEANERA,
    ("EVEN", "quinceanera"): EventType.QUINCEANERA,
    ("EVEN", "contrato bracero"): EventType.BRACERO_CONTRACT,
    ("EVEN", "bracero contract"): EventType.BRACERO_CONTRACT,
    ("EVEN", "cruce fronterizo"): EventType.BORDER_CROSSING,
    ("EVEN", "border crossing"): EventType.BORDER_CROSSING,
}

_UNTYPED: dict[str, EventType] = {
    spec.gedcom_tag: event_type
    for event_type, spec in _SPECS.items()
    if spec.gedcom_type is None and event_type is not EventType.OTHER
}


def event_type_from_gedcom(tag: str, type_text: str | None = None) -> EventType:
    """Map a GEDCOM 7 event tag (and optional `TYPE`) to an `EventType`.

    An unknown `TYPE` on `MARR` gives the generic `MARRIAGE`; any `EVEN` without a known
    `TYPE` gives `OTHER` (the caller keeps the TYPE text). Raises `ValueError` for tags that
    are not events this vocabulary knows.
    """
    upper = tag.upper()
    if type_text:
        known = _TYPE_ALIASES.get((upper, _fold(type_text)))
        if known is not None:
            return known
    if upper == "EVEN":
        return EventType.OTHER
    if upper in _UNTYPED:
        return _UNTYPED[upper]
    raise ValueError(f"{tag!r} is not a known GEDCOM event tag")


class AssociationRole(StrEnum):
    """A person's role at someone else's event, mapped to GEDCOM 7 `ROLE` values."""

    GODPARENT = "GODP"
    WITNESS = "WITN"
    OFFICIANT = "OFFICIATOR"
    CLERGY = "CLERGY"
    OTHER = "OTHER"

    @property
    def label_es(self) -> str:
        return _ROLE_LABELS[self][0]

    @property
    def label_en(self) -> str:
        return _ROLE_LABELS[self][1]

    def gedcom_role(self, phrase: str | None = None) -> tuple[str, str | None]:
        """Return `(ROLE payload, PHRASE)`. `OTHER` requires a phrase («Chambelán», …)."""
        if self is AssociationRole.OTHER:
            if not phrase or not phrase.strip():
                raise ValueError("ROLE OTHER needs a PHRASE describing the role")
            return self.value, phrase.strip()
        return self.value, phrase.strip() if phrase and phrase.strip() else None


_ROLE_LABELS: dict[AssociationRole, tuple[str, str]] = {
    AssociationRole.GODPARENT: ("Padrino o madrina", "Godparent"),
    AssociationRole.WITNESS: ("Testigo", "Witness"),
    AssociationRole.OFFICIANT: ("Oficiante", "Officiant"),
    AssociationRole.CLERGY: ("Sacerdote o ministro", "Clergy"),
    AssociationRole.OTHER: ("Otro papel", "Other role"),
}


def role_from_gedcom(value: str) -> AssociationRole:
    """Map a GEDCOM 7 `ROLE` payload to an `AssociationRole`; unknown roles become `OTHER`."""
    try:
        return AssociationRole(value.upper())
    except ValueError:
        return AssociationRole.OTHER
