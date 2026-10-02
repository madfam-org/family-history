"""Mapping helpers between Mexican family-history concepts and GEDCOM 7.0 structures.

Pure functions over plain dataclasses and `Structure` nodes; nothing here imports the domain
layer. Each concept maps to standard GEDCOM first and adds a documented MADFAM extension only
for what the standard cannot say (docs/GEDCOM.md, "Mexican mappings"):

* two surnames -> ``SURN`` pieces in display order, each with ``_FH_SURNAME_LINE``, plus
  ``_FH_SURNAME_ORDER`` on the ``NAME``;
* apodos -> ``NICK``;
* padrinos per sacrament -> ``ASSO`` + ``ROLE GODP`` (+ ``PHRASE``) under the sacrament event;
* civil vs religious marriage -> ``MARR`` + ``TYPE`` + ``_FH_EVENT_KIND``; unión libre ->
  ``EVEN`` + ``TYPE``;
* XV años, bracero contract, border crossing -> ``EVEN`` + ``TYPE`` + ``_FH_EVENT_KIND``;
* sensitivity class -> ``_FH_SENSITIVITY`` and, for living people, ``RESN CONFIDENTIAL``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from family_history.gedcom.datatypes import split_list
from family_history.gedcom.extensions import EVENT_KIND, SENSITIVITY, SURNAME_LINE, SURNAME_ORDER
from family_history.gedcom.model_parts import EVENT_TAGS
from family_history.gedcom.structure import VOID, Structure


class SurnameLine(StrEnum):
    PATERNAL = "PATERNAL"
    MATERNAL = "MATERNAL"
    OTHER = "OTHER"


class SurnameOrder(StrEnum):
    PATERNAL_FIRST = "PATERNAL_FIRST"
    MATERNAL_FIRST = "MATERNAL_FIRST"


class Sensitivity(StrEnum):
    RELIGION = "RELIGION"
    HEALTH = "HEALTH"
    GENETIC = "GENETIC"
    ETHNICITY = "ETHNICITY"
    SEXUAL = "SEXUAL"
    POLITICAL = "POLITICAL"


class Sacrament(StrEnum):
    BAPTISM = "BAPM"
    CONFIRMATION = "CONF"
    FIRST_COMMUNION = "FCOM"
    RELIGIOUS_MARRIAGE = "MARR"


class EventKind(StrEnum):
    CIVIL_MARRIAGE = "CIVIL_MARRIAGE"
    RELIGIOUS_MARRIAGE = "RELIGIOUS_MARRIAGE"
    FREE_UNION = "FREE_UNION"
    QUINCEANERA = "QUINCEANERA"
    BRACERO_CONTRACT = "BRACERO_CONTRACT"
    BORDER_CROSSING = "BORDER_CROSSING"


UNION_KINDS = frozenset(
    {EventKind.CIVIL_MARRIAGE, EventKind.RELIGIOUS_MARRIAGE, EventKind.FREE_UNION}
)

#: Spanish ``TYPE`` text written for each kind (families read it; es-MX first).
KIND_LABELS: dict[EventKind, str] = {
    EventKind.CIVIL_MARRIAGE: "Matrimonio civil",
    EventKind.RELIGIOUS_MARRIAGE: "Matrimonio religioso",
    EventKind.FREE_UNION: "Unión libre",
    EventKind.QUINCEANERA: "XV años",
    EventKind.BRACERO_CONTRACT: "Contrato bracero",
    EventKind.BORDER_CROSSING: "Cruce fronterizo",
}

_KIND_SYNONYMS: dict[str, EventKind] = {
    "matrimonio civil": EventKind.CIVIL_MARRIAGE, "civil": EventKind.CIVIL_MARRIAGE,
    "civil marriage": EventKind.CIVIL_MARRIAGE, "registro civil": EventKind.CIVIL_MARRIAGE,
    "matrimonio religioso": EventKind.RELIGIOUS_MARRIAGE,
    "religioso": EventKind.RELIGIOUS_MARRIAGE, "religious": EventKind.RELIGIOUS_MARRIAGE,
    "religious marriage": EventKind.RELIGIOUS_MARRIAGE, "iglesia": EventKind.RELIGIOUS_MARRIAGE,
    "matrimonio eclesiastico": EventKind.RELIGIOUS_MARRIAGE,
    "church": EventKind.RELIGIOUS_MARRIAGE, "union libre": EventKind.FREE_UNION,
    "free union": EventKind.FREE_UNION, "concubinato": EventKind.FREE_UNION,
    "common law marriage": EventKind.FREE_UNION, "xv anos": EventKind.QUINCEANERA,
    "xv": EventKind.QUINCEANERA, "quince anos": EventKind.QUINCEANERA,
    "quinceanera": EventKind.QUINCEANERA, "fiesta de xv anos": EventKind.QUINCEANERA,
    "contrato bracero": EventKind.BRACERO_CONTRACT, "bracero": EventKind.BRACERO_CONTRACT,
    "programa bracero": EventKind.BRACERO_CONTRACT,
    "bracero contract": EventKind.BRACERO_CONTRACT,
    "cruce fronterizo": EventKind.BORDER_CROSSING, "border crossing": EventKind.BORDER_CROSSING,
    "cruce de frontera": EventKind.BORDER_CROSSING,
}

#: Event tags whose facts default to the religion sensitivity class.
RELIGIOUS_TAGS = frozenset({"BAPM", "CHR", "CHRA", "CONF", "FCOM", "BARM", "BASM", "BLES",
                            "ORDN", "RELI"})
#: Tags under which ``RESN`` is permitted (records, events and attributes).
_RESN_TAGS = EVENT_TAGS | {"INDI", "FAM", "OBJE"}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.replace("-", " ").split())


def _no_slash(value: str | None, what: str) -> None:
    if value is not None and "/" in value:
        raise ValueError(f"{what} cannot contain '/': GEDCOM uses it to delimit surnames")


# -- names --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MexicanName:
    """A name with nombre(s) de pila, apellido paterno, apellido materno and apodos."""

    given: str | None = None
    paternal_surname: str | None = None
    maternal_surname: str | None = None
    nicknames: tuple[str, ...] = ()
    order: SurnameOrder = SurnameOrder.PATERNAL_FIRST
    prefix: str | None = None
    suffix: str | None = None
    name_type: str | None = None

    def surnames_in_order(self) -> list[tuple[SurnameLine, str]]:
        pairs = [
            (SurnameLine.PATERNAL, self.paternal_surname),
            (SurnameLine.MATERNAL, self.maternal_surname),
        ]
        if self.order is SurnameOrder.MATERNAL_FIRST:
            pairs.reverse()
        return [(line, value) for line, value in pairs if value]


def name_to_structure(name: MexicanName) -> Structure:
    """Build a 7.0 ``NAME`` structure, e.g. ``María /Hernández López/``."""
    for value, what in ((name.given, "given name"), (name.paternal_surname, "surname"),
                        (name.maternal_surname, "surname"), (name.prefix, "prefix"),
                        (name.suffix, "suffix")):
        _no_slash(value, what)
    surnames = name.surnames_in_order()
    front = " ".join(p for p in (name.prefix, name.given) if p)
    payload = f"{front} /{' '.join(v for _, v in surnames)}/".strip() if surnames else front
    if name.suffix:
        payload = f"{payload} {name.suffix}"
    node = Structure(tag="NAME", payload=payload or None)
    if name.name_type:
        node.add("TYPE", name.name_type)
    if name.prefix:
        node.add("NPFX", name.prefix)
    if name.given:
        node.add("GIVN", name.given)
    for nickname in name.nicknames:
        node.add("NICK", nickname)
    for line, value in surnames:
        node.add("SURN", value).add(SURNAME_LINE.tag, line.value)
    if name.suffix:
        node.add("NSFX", name.suffix)
    if surnames:
        node.add(SURNAME_ORDER.tag, name.order.value)
    return node


def name_from_structure(node: Structure) -> MexicanName:
    """Read a ``NAME`` structure back, with or without the MADFAM extensions.

    Without ``_FH_SURNAME_LINE`` markers, the first two ``SURN`` pieces (or, with no pieces,
    the two words between the slashes) are taken as paterno and materno in display order.
    """
    order_text = node.text(SURNAME_ORDER.tag) or ""
    order = (
        SurnameOrder(order_text)
        if order_text in SurnameOrder.__members__
        else SurnameOrder.PATERNAL_FIRST
    )
    payload = node.payload or ""
    given = " ".join(p.payload for p in node.all("GIVN") if p.payload) or None
    if given is None:
        given = payload.split("/")[0].strip() or None
    paternal, maternal = _surnames(node, payload, order)
    return MexicanName(
        given=given,
        paternal_surname=paternal,
        maternal_surname=maternal,
        nicknames=tuple(p.payload for p in node.all("NICK") if p.payload),
        order=order,
        prefix=node.text("NPFX"),
        suffix=node.text("NSFX"),
        name_type=node.text("TYPE"),
    )


def _surnames(node: Structure, payload: str, order: SurnameOrder) -> tuple[str | None, str | None]:
    pieces = [p for p in node.all("SURN") if p.payload]
    marked = {p.text(SURNAME_LINE.tag): p.payload for p in pieces if p.text(SURNAME_LINE.tag)}
    if SurnameLine.PATERNAL in marked or SurnameLine.MATERNAL in marked:
        return marked.get(SurnameLine.PATERNAL), marked.get(SurnameLine.MATERNAL)
    values = [p.payload or "" for p in pieces]
    if not values and payload.count("/") == 2:
        inside = payload.split("/")[1].split()
        values = inside if len(inside) == 2 else ([" ".join(inside)] if inside else [])
    if order is SurnameOrder.MATERNAL_FIRST:
        values.reverse()
        maternal = values[1] if len(values) > 1 else (values[0] if values else None)
        paternal = values[0] if len(values) > 1 else None
        return paternal, maternal
    return (values[0] if values else None), (values[1] if len(values) > 1 else None)


# -- godparents ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Godparent:
    """A padrino or madrina: a pointer to their INDI (or ``@VOID@``) and an optional phrase."""

    pointer: str = VOID
    phrase: str | None = None


def godparent_association(godparent: Godparent) -> Structure:
    node = Structure(tag="ASSO", pointer=godparent.pointer)
    role = node.add("ROLE", "GODP")
    if godparent.phrase:
        role.add("PHRASE", godparent.phrase)
    return node


def godparents_from_event(event: Structure) -> list[Godparent]:
    """Every ``ASSO`` with ``ROLE GODP`` directly under ``event``."""
    found: list[Godparent] = []
    for asso in event.all("ASSO"):
        role = asso.first("ROLE")
        if role is not None and role.payload == "GODP":
            phrase = role.text("PHRASE") or asso.text("PHRASE")
            found.append(Godparent(asso.pointer or VOID, phrase))
    return found


def sacrament_event(
    sacrament: Sacrament,
    *,
    date: str | None = None,
    place: str | None = None,
    godparents: Iterable[Godparent] = (),
    subject_living: bool = False,
) -> Structure:
    """A sacrament with its padrinos; it always carries the religion sensitivity class."""
    if sacrament is Sacrament.RELIGIOUS_MARRIAGE:
        node = event_structure(EventKind.RELIGIOUS_MARRIAGE, date=date, place=place)
    else:
        node = Structure(tag=sacrament.value)
        _date_place(node, date, place)
    node.children.extend(godparent_association(g) for g in godparents)
    return apply_sensitivity(node, {Sensitivity.RELIGION}, subject_living=subject_living)


# -- unions and Mexican events -------------------------------------------------------------


def _date_place(node: Structure, date: str | None, place: str | None) -> None:
    if date is not None:
        node.add("DATE", date)
    if place is not None:
        node.add("PLAC", place)


def event_structure(
    kind: EventKind, *, date: str | None = None, place: str | None = None,
    label: str | None = None,
) -> Structure:
    """``MARR`` for civil and religious marriages, ``EVEN`` for everything else.

    ``label`` overrides the Spanish ``TYPE`` text; the kind stays machine-readable in
    ``_FH_EVENT_KIND`` either way. A religious marriage also gets the religion sensitivity.
    """
    tag = "MARR" if kind in (EventKind.CIVIL_MARRIAGE, EventKind.RELIGIOUS_MARRIAGE) else "EVEN"
    node = Structure(tag=tag)
    node.add("TYPE", label or KIND_LABELS[kind])
    _date_place(node, date, place)
    node.add(EVENT_KIND.tag, kind.value)
    if kind is EventKind.RELIGIOUS_MARRIAGE:
        node = apply_sensitivity(node, {Sensitivity.RELIGION}, subject_living=False)
    return node


def event_kind(node: Structure) -> EventKind | None:
    """The kind of an event: the extension if present, else recognized ``TYPE`` text."""
    marker = node.text(EVENT_KIND.tag) or ""
    if marker in EventKind.__members__:
        return EventKind(marker)
    type_text = node.text("TYPE")
    if type_text is None:
        return None
    kind = _KIND_SYNONYMS.get(_fold(type_text))
    if kind is None:
        return None
    if node.tag == "MARR" and kind not in (EventKind.CIVIL_MARRIAGE, EventKind.RELIGIOUS_MARRIAGE):
        return None
    return kind


def union_kind(node: Structure) -> EventKind | None:
    """Civil marriage, religious marriage or unión libre; ``None`` for anything else."""
    kind = event_kind(node)
    return kind if kind in UNION_KINDS else None


# -- sensitivity ---------------------------------------------------------------------------


def sensitivity_of(node: Structure) -> frozenset[Sensitivity]:
    """The classes declared in ``_FH_SENSITIVITY`` (unknown values are ignored)."""
    value = node.text(SENSITIVITY.tag)
    if not value:
        return frozenset()
    return frozenset(Sensitivity(v) for v in split_list(value) if v in Sensitivity.__members__)


def default_sensitivity(node: Structure) -> frozenset[Sensitivity]:
    """Classes a fact carries by default (PRIVACY.md rule 2)."""
    if node.tag in RELIGIOUS_TAGS or event_kind(node) is EventKind.RELIGIOUS_MARRIAGE:
        return frozenset({Sensitivity.RELIGION})
    if node.tag == "CAUS":
        return frozenset({Sensitivity.HEALTH})
    return frozenset()


def apply_sensitivity(
    node: Structure, classes: Iterable[Sensitivity], *, subject_living: bool
) -> Structure:
    """A copy of ``node`` carrying ``classes`` (merged with any already declared).

    When the subject is living and the fact is sensitive, ``RESN CONFIDENTIAL`` is added too,
    on structures where the specification permits ``RESN`` (records, events, attributes); for
    others, such as ``CAUS``, set it on the enclosing event.
    """
    result = node.copy()
    merged = sensitivity_of(result) | frozenset(classes)
    result.children = [c for c in result.children if c.tag != SENSITIVITY.tag]
    if not merged:
        return result
    result.add(SENSITIVITY.tag, ", ".join(sorted(c.value for c in merged)))
    if subject_living and result.tag in _RESN_TAGS:
        resn = result.first("RESN")
        if resn is None:
            result.children.insert(0, Structure(tag="RESN", payload="CONFIDENTIAL"))
        else:
            values = split_list(resn.payload or "")
            if "CONFIDENTIAL" not in values:
                resn.payload = ", ".join([v for v in values if v] + ["CONFIDENTIAL"])
    return result
