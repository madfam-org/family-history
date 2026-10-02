"""The Mexican name model: `NameForm` and its display styles.

A name is stored as the person (or the record) gave it. Nothing here derives a married name:
in Mexico a woman keeps both of her surnames for life, so a married form exists only when a
record states one and someone enters it as a `NameType.MARRIED` form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "PARTICLES",
    "DisplayStyle",
    "NameForm",
    "NameType",
    "SurnameOrder",
    "display_name",
]

#: Lower-case surname particles accepted before a surname (Spanish, Portuguese and a few others
#: binational families bring).
PARTICLES: frozenset[str] = frozenset(
    {
        "de", "del", "de la", "de las", "de los", "la", "las", "los",
        "da", "das", "do", "dos", "di", "van", "von", "van der", "mc", "o'",
    }
)  # fmt: skip

#: Words that may join the two surnames: «Pérez y González», «Gómez e Ibarra».
_JOINERS: frozenset[str] = frozenset({"y", "e", "-"})

_BCP47 = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class NameType(StrEnum):
    """Why a name form exists. Labels via `label_es` / `label_en`."""

    BIRTH = "birth"
    BAPTISM = "baptism"
    CIVIL = "civil"
    MARRIED = "married"
    AKA = "aka"
    RELIGIOUS = "religious"
    IMMIGRANT = "immigrant"
    INDIGENOUS = "indigenous"
    PROFESSIONAL = "professional"

    @property
    def label_es(self) -> str:
        return _NAME_TYPE_LABELS[self][0]

    @property
    def label_en(self) -> str:
        return _NAME_TYPE_LABELS[self][1]

    @property
    def gedcom_type(self) -> tuple[str, str | None]:
        """The GEDCOM 7 `NAME.TYPE` value and, for `OTHER`, the PHRASE to write with it."""
        tag = _GEDCOM_NAME_TYPES.get(self)
        if tag is not None:
            return tag, None
        return "OTHER", self.label_es


_NAME_TYPE_LABELS: dict[NameType, tuple[str, str]] = {
    NameType.BIRTH: ("Nombre de nacimiento", "Birth name"),
    NameType.BAPTISM: ("Nombre de bautizo", "Baptismal name"),
    NameType.CIVIL: ("Nombre en el Registro Civil", "Civil registration name"),
    NameType.MARRIED: ("Nombre de casada o casado", "Married name"),
    NameType.AKA: ("También conocido como", "Also known as"),
    NameType.RELIGIOUS: ("Nombre religioso", "Religious name"),
    NameType.IMMIGRANT: ("Nombre de inmigrante", "Immigrant name"),
    NameType.INDIGENOUS: ("Nombre en lengua indígena", "Indigenous-language name"),
    NameType.PROFESSIONAL: ("Nombre profesional", "Professional name"),
}

_GEDCOM_NAME_TYPES: dict[NameType, str] = {
    NameType.BIRTH: "BIRTH",
    NameType.MARRIED: "MARRIED",
    NameType.AKA: "AKA",
    NameType.IMMIGRANT: "IMMIGRANT",
    NameType.PROFESSIONAL: "PROFESSIONAL",
}


class SurnameOrder(StrEnum):
    """How the two surnames are written and which one a list sorts by.

    - `PATERNO_FIRST`: the Mexican default, «López Hernández»; sorts by the paternal surname.
    - `MATERNO_FIRST`: the mother's surname first, which the SCJN recognised as a right in
      Amparo en Revisión 208/2016; it is the first surname, so lists sort by it.
    - `PT_BR`: Brazilian order, mother's surname then father's («Souza Silva»); lists sort by
      the last surname, the father's.
    """

    PATERNO_FIRST = "paterno_first"
    MATERNO_FIRST = "materno_first"
    PT_BR = "pt_BR"


class DisplayStyle(StrEnum):
    """`FULL`: everything incl. apodos; `FORMAL`: as on a document; `SHORT`: everyday;
    `SORTING`: surnames first, for alphabetical lists."""

    FULL = "full"
    FORMAL = "formal"
    SHORT = "short"
    SORTING = "sorting"


@dataclass(frozen=True, slots=True)
class NameForm:
    """One name of one person, as a record or the family states it.

    `given_names` holds each given name; an item may itself be compound («María de Jesús»,
    «José María»). `nombre_usado` is the given name the person went by, when it differs from
    the full nombre de pila. Particles are stored apart from the surname they precede so lists
    sort by the surname proper (RAE convention): «Garza y Treviño, Ignacio de la».
    """

    given_names: tuple[str, ...] = ()
    apellido_paterno: str | None = None
    apellido_materno: str | None = None
    particle_paterno: str | None = None
    particle_materno: str | None = None
    surname_joiner: str | None = None
    extra_surnames: tuple[str, ...] = ()
    nombre_usado: str | None = None
    apodos: tuple[str, ...] = ()
    name_type: NameType = NameType.BIRTH
    lang: str = "es-MX"
    surname_order: SurnameOrder = SurnameOrder.PATERNO_FIRST

    def __post_init__(self) -> None:
        for label, values in (
            ("given_names", self.given_names),
            ("extra_surnames", self.extra_surnames),
            ("apodos", self.apodos),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{label} must not contain blank entries")
        for label, value in (
            ("apellido_paterno", self.apellido_paterno),
            ("apellido_materno", self.apellido_materno),
            ("nombre_usado", self.nombre_usado),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{label} must be None or non-blank")
        for label, particle, surname in (
            ("particle_paterno", self.particle_paterno, self.apellido_paterno),
            ("particle_materno", self.particle_materno, self.apellido_materno),
        ):
            if particle is None:
                continue
            if particle.lower() not in PARTICLES:
                raise ValueError(f"{label} {particle!r} is not a known particle")
            if surname is None:
                raise ValueError(f"{label} needs its surname")
        if self.surname_joiner is not None and self.surname_joiner.lower() not in _JOINERS:
            raise ValueError("surname_joiner must be «y», «e» or «-»")
        if not _BCP47.match(self.lang):
            raise ValueError(f"lang {self.lang!r} is not a BCP 47 tag")
        if not (self.given_names or self.apellido_paterno or self.apellido_materno
                or self.extra_surnames or self.apodos):  # fmt: skip
            raise ValueError("a name form needs at least one given name, surname or apodo")

    @property
    def nombre_de_pila(self) -> str:
        """All given names, as on the birth or baptism record."""
        return " ".join(self.given_names)

    @property
    def first_surname(self) -> str | None:
        """The surname written first under `surname_order`, with its particle."""
        parts = self._ordered_surnames()
        return parts[0] if parts else None

    def _paterno(self) -> str | None:
        return _with_particle(self.particle_paterno, self.apellido_paterno)

    def _materno(self) -> str | None:
        return _with_particle(self.particle_materno, self.apellido_materno)

    def _ordered_surnames(self) -> list[str]:
        if self.surname_order is SurnameOrder.PATERNO_FIRST:
            pair = [self._paterno(), self._materno()]
        else:
            pair = [self._materno(), self._paterno()]
        return [surname for surname in pair if surname]

    def surnames_text(self) -> str:
        """Both surnames in display order, with the joiner, then any extra surnames."""
        ordered = self._ordered_surnames()
        joiner = f" {self.surname_joiner} " if self.surname_joiner and len(ordered) == 2 else " "
        if self.surname_joiner == "-" and len(ordered) == 2:
            joiner = "-"
        return " ".join(part for part in (joiner.join(ordered), *self.extra_surnames) if part)

    def sort_surname(self) -> str:
        """The surname proper a list sorts by (no particle), per `surname_order`."""
        if self.surname_order is SurnameOrder.MATERNO_FIRST:
            order = (self.apellido_materno, self.apellido_paterno)
        else:
            order = (self.apellido_paterno, self.apellido_materno)
        for surname in (*order, *self.extra_surnames):
            if surname:
                return surname
        return ""


def _with_particle(particle: str | None, surname: str | None) -> str | None:
    if surname is None:
        return None
    return f"{particle} {surname}" if particle else surname


def display_name(form: NameForm, style: DisplayStyle = DisplayStyle.FULL) -> str:
    """Render `form` in `style`.

    - FULL: «María de Jesús «Chuy» López Hernández».
    - FORMAL: «María de Jesús López Hernández».
    - SHORT: nombre usado (or the first given name) and the first surname: «Jesús López»;
      Brazilian order uses the last (paternal) surname: «João Silva».
    - SORTING: «López Hernández, María de Jesús»; particles move after the given names
      («Garza y Treviño, Ignacio de la»); Brazilian order sorts by the last surname
      («Silva, João Souza»).
    """
    surnames = form.surnames_text()
    given = form.nombre_de_pila
    if style is DisplayStyle.SHORT:
        first_given = form.nombre_usado or (form.given_names[0] if form.given_names else "")
        surname = form.first_surname or ""
        if form.surname_order is SurnameOrder.PT_BR and form.apellido_paterno:
            surname = form._paterno() or ""
        short = " ".join(part for part in (first_given, surname) if part)
        return short or (form.apodos[0] if form.apodos else surnames)
    if style is DisplayStyle.SORTING:
        return _sorting(form)
    nickname = ""
    if style is DisplayStyle.FULL and form.apodos:
        nickname = " ".join(f"«{apodo}»" for apodo in form.apodos)
    return " ".join(part for part in (given, nickname, surnames) if part)


def _sorting(form: NameForm) -> str:
    paterno = (form.particle_paterno, form.apellido_paterno)
    materno = (form.particle_materno, form.apellido_materno)
    lead, other = (materno, paterno) if form.surname_order is SurnameOrder.MATERNO_FIRST else (
        paterno,
        materno,
    )
    if lead[1] is None:
        lead, other = other, (None, None)
    lead_particle, lead_surname = lead
    head_parts = [lead_surname] if lead_surname else []
    tail_parts = [form.nombre_de_pila] if form.given_names else []
    other_text = _with_particle(*other)
    if other_text:
        if form.surname_order is SurnameOrder.PT_BR:
            tail_parts.append(other_text)
        elif form.surname_joiner == "-":
            head_parts[-1] = f"{head_parts[-1]}-{other_text}"
        else:
            if form.surname_joiner:
                head_parts.append(form.surname_joiner)
            head_parts.append(other_text)
    head_parts.extend(form.extra_surnames)
    if lead_particle:
        tail_parts.append(lead_particle)
    head, tail = " ".join(head_parts), " ".join(tail_parts)
    if head and tail:
        return f"{head}, {tail}"
    return head or tail or form.apodos[0]
