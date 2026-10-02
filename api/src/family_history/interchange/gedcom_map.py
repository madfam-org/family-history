"""Vocabulary tables shared by the GEDCOM exporter and importer, so each mapping is one table
read in both directions."""

from __future__ import annotations

import unicodedata

from family_history.domain.events import EventType
from family_history.domain.names import PARTICLES
from family_history.gedcom import mexico
from family_history.interchange.tree import TPlace
from family_history.models.enums import AssociationRole, NameType, ParticipantRole

#: `HEAD.SOUR` of our exports. A file carrying it states every sensitivity class explicitly, so
#: the importer adds no defaults to it.
PRODUCT = "FAMILY_HISTORY"

#: Attributes whose payload is the description (GEDCOM 7 `OCCU`, `EDUC`, `RESI` take text).
ATTRIBUTE_TYPES = frozenset({EventType.OCCUPATION, EventType.EDUCATION, EventType.RESIDENCE})

MEXICO_KINDS: dict[EventType, mexico.EventKind] = {
    EventType.CIVIL_MARRIAGE: mexico.EventKind.CIVIL_MARRIAGE,
    EventType.RELIGIOUS_MARRIAGE: mexico.EventKind.RELIGIOUS_MARRIAGE,
    EventType.QUINCEANERA: mexico.EventKind.QUINCEANERA,
    EventType.BRACERO_CONTRACT: mexico.EventKind.BRACERO_CONTRACT,
    EventType.BORDER_CROSSING: mexico.EventKind.BORDER_CROSSING,
}
KIND_TYPES: dict[mexico.EventKind, EventType] = {kind: t for t, kind in MEXICO_KINDS.items()}

STEP_PHRASE = "Hijastro o hijastra"
#: Pedigree → (`PEDI`, `PHRASE`); birth is the default and writes no `PEDI`.
PEDIGREE_TO_GEDCOM: dict[str, tuple[str, str | None]] = {
    "adopted": ("ADOPTED", None),
    "foster": ("FOSTER", None),
    "step": ("OTHER", STEP_PHRASE),
}

SURNAME_ORDER_TO_GEDCOM: dict[str, mexico.SurnameOrder] = {
    "paterno_materno": mexico.SurnameOrder.PATERNAL_FIRST,
    "materno_paterno": mexico.SurnameOrder.MATERNAL_FIRST,
    "single": mexico.SurnameOrder.PATERNAL_FIRST,
}

_NAME_TYPES: dict[str, tuple[str, str | None]] = {
    NameType.BIRTH.value: ("BIRTH", None),
    NameType.MARRIED.value: ("MARRIED", None),
    NameType.ALSO_KNOWN_AS.value: ("AKA", None),
    NameType.IMMIGRANT.value: ("IMMIGRANT", None),
    NameType.BAPTISMAL.value: ("OTHER", "Nombre de bautizo"),
    NameType.RELIGIOUS.value: ("OTHER", "Nombre religioso"),
    NameType.OTHER.value: ("OTHER", "Otro nombre"),
}
_NAME_TYPES_BACK: dict[tuple[str, str | None], str] = {v: k for k, v in _NAME_TYPES.items()}

_PARTICIPANT_ROLES: dict[str, tuple[str, str | None]] = {
    ParticipantRole.PARENT.value: ("PARENT", None),
    ParticipantRole.SPOUSE.value: ("SPOU", None),
    ParticipantRole.GODPARENT.value: ("GODP", None),
    ParticipantRole.WITNESS.value: ("WITN", None),
    ParticipantRole.OFFICIANT.value: ("OFFICIATOR", None),
    ParticipantRole.INFORMANT.value: ("OTHER", "Informante"),
    ParticipantRole.OTHER.value: ("OTHER", "Otro participante"),
}
_ASSOCIATION_ROLES: dict[str, str] = {
    AssociationRole.GODPARENT.value: "GODP",
    AssociationRole.WITNESS.value: "WITN",
    AssociationRole.OFFICIANT.value: "OFFICIATOR",
    AssociationRole.OTHER.value: "OTHER",
}
OTHER_ROLE_PHRASE = "Otro papel"


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def name_type_to_gedcom(name_type: str) -> tuple[str, str | None]:
    return _NAME_TYPES.get(name_type, ("OTHER", "Otro nombre"))


def name_type_from_gedcom(value: str | None, phrase: str | None) -> str:
    if not value:
        return NameType.BIRTH.value
    upper = value.upper()
    if upper == "OTHER":
        return _NAME_TYPES_BACK.get(("OTHER", phrase), NameType.OTHER.value)
    if upper == "MAIDEN":
        return NameType.BIRTH.value
    return _NAME_TYPES_BACK.get((upper, None), NameType.ALSO_KNOWN_AS.value)


def participant_role(role: str) -> tuple[str, str | None]:
    return _PARTICIPANT_ROLES.get(role, ("OTHER", "Otro participante"))


def association_role(role: str, phrase: str | None) -> tuple[str, str | None]:
    code = _ASSOCIATION_ROLES.get(role, "OTHER")
    if code == "OTHER" and not phrase:
        phrase = OTHER_ROLE_PHRASE
    return code, phrase


def role_from_gedcom(role: str, phrase: str | None) -> tuple[str, str, str | None]:
    """`ASSO.ROLE` → ("participant" | "association", role, phrase)."""
    upper = role.upper()
    if upper in ("PARENT", "FATH", "MOTH"):
        return "participant", ParticipantRole.PARENT.value, None
    if upper in ("SPOU", "HUSB", "WIFE"):
        return "participant", ParticipantRole.SPOUSE.value, None
    if upper == "OTHER" and phrase == "Informante":
        return "participant", ParticipantRole.INFORMANT.value, None
    if upper == "OTHER" and phrase == "Otro participante":
        return "participant", ParticipantRole.OTHER.value, None
    if upper == "GODP":
        return "association", AssociationRole.GODPARENT.value, phrase
    if upper == "WITN":
        return "association", AssociationRole.WITNESS.value, phrase
    if upper in ("OFFICIATOR", "CLERGY"):
        return "association", AssociationRole.OFFICIANT.value, phrase
    return "association", AssociationRole.OTHER.value, phrase or upper.capitalize()


def pedigree_from_gedcom(value: str | None, phrase: str | None) -> tuple[str, str | None]:
    """(pedigree, warning code or None)."""
    upper = (value or "BIRTH").upper()
    if upper == "BIRTH":
        return "birth", None
    if upper == "ADOPTED":
        return "adopted", None
    if upper == "FOSTER":
        return "foster", None
    if upper == "OTHER" and phrase and fold(phrase) in {fold(STEP_PHRASE), "step", "hijastro",
                                                        "hijastra", "hijastro/a"}:  # fmt: skip
        return "step", None
    if upper == "SEALING":
        return "birth", "pedigree_sealing"
    return "foster", "pedigree_other"


def split_particle(surname: str | None) -> tuple[str | None, str | None]:
    """«de la Garza» → («de la», «Garza»): a leading known particle is stored apart."""
    if not surname:
        return None, surname
    words = surname.split(" ")
    for size in (2, 1):
        if len(words) > size:
            head = " ".join(words[:size])
            if head.lower() in PARTICLES:
                return head, " ".join(words[size:])
    return None, surname


def place_paths(places: list[TPlace]) -> dict[str, str]:
    """`PLAC` payloads: each place's name, then its parents', up to the root."""
    by_ref = {p.ref: p for p in places}
    out: dict[str, str] = {}
    for place in places:
        names: list[str] = []
        current: TPlace | None = place
        while current is not None and len(names) < 64:
            names.append(current.name)
            current = by_ref.get(current.parent) if current.parent else None
        out[place.ref] = ", ".join(names)
    return out
