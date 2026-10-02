"""Compadrazgo: godparenthood and the compadre bond it creates.

Only the godparent association is stored (who sponsored whom, at which sacrament or
celebration). Everything else is derived here and never stored:

- the godparent is the padrino/madrina of the godchild, who is their ahijado/ahijada;
- the godchild's parents (by birth or adoption) and the godparent become compadres and
  comadres of each other.

For a wedding, the godchild is each spouse: the padrinos de boda sponsor the couple and become
compadres of both spouses' parents.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .events import EventType
from .kinship import FamilyGraph, Sex

__all__ = [
    "CompadrazgoRelation",
    "CompadrazgoRole",
    "GodparentLink",
    "Occasion",
    "compadrazgo",
]


class Occasion(StrEnum):
    """The sacrament or celebration a godparent sponsored."""

    BAUTIZO = "bautizo"
    CONFIRMACION = "confirmacion"
    PRIMERA_COMUNION = "primera_comunion"
    BODA = "boda"
    XV_ANOS = "xv_anos"
    PRESENTACION = "presentacion"

    @property
    def label_es(self) -> str:
        return _OCCASIONS[self][0]

    @property
    def label_en(self) -> str:
        return _OCCASIONS[self][1]

    @property
    def event_type(self) -> EventType:
        """The event the association hangs from (GEDCOM `ASSO` with `ROLE GODP`)."""
        return _OCCASIONS[self][2]


_OCCASIONS: dict[Occasion, tuple[str, str, EventType]] = {
    Occasion.BAUTIZO: ("bautizo", "baptism", EventType.BAPTISM),
    Occasion.CONFIRMACION: ("confirmación", "confirmation", EventType.CONFIRMATION),
    Occasion.PRIMERA_COMUNION: (
        "primera comunión",
        "first communion",
        EventType.FIRST_COMMUNION,
    ),
    Occasion.BODA: ("boda", "wedding", EventType.RELIGIOUS_MARRIAGE),
    Occasion.XV_ANOS: ("XV años", "quinceañera", EventType.QUINCEANERA),
    Occasion.PRESENTACION: ("presentación", "presentation", EventType.OTHER),
}


@dataclass(frozen=True, slots=True)
class GodparentLink:
    """`godparent` sponsored `godchild` at `occasion`. The only stored compadrazgo fact."""

    godparent: str
    godchild: str
    occasion: Occasion

    def __post_init__(self) -> None:
        if self.godparent == self.godchild:
            raise ValueError("a person cannot be their own godparent")


class CompadrazgoRole(StrEnum):
    """What the other person is to ego."""

    GODPARENT = "godparent"
    GODCHILD = "godchild"
    COMPADRE = "compadre"


@dataclass(frozen=True, slots=True)
class CompadrazgoRelation:
    """A derived relation: `alter` is ego's `role` through `godchild` at `occasion`."""

    role: CompadrazgoRole
    alter: str
    occasion: Occasion
    godchild: str
    label_es: str
    label_en: str


_NOUNS: dict[CompadrazgoRole, tuple[tuple[str, str, str], tuple[str, str, str]]] = {
    CompadrazgoRole.GODPARENT: (
        ("padrino", "madrina", "padrino/madrina"),
        ("godfather", "godmother", "godparent"),
    ),
    CompadrazgoRole.GODCHILD: (
        ("ahijado", "ahijada", "ahijado/a"),
        ("godson", "goddaughter", "godchild"),
    ),
    CompadrazgoRole.COMPADRE: (
        ("compadre", "comadre", "compadre/comadre"),
        ("compadre", "comadre", "compadre/comadre"),
    ),
}


def _labels(role: CompadrazgoRole, sex: Sex, occasion: Occasion) -> tuple[str, str]:
    index = 0 if sex is Sex.MALE else 1 if sex is Sex.FEMALE else 2
    spanish, english = _NOUNS[role]
    return (
        f"{spanish[index]} de {occasion.label_es}",
        f"{english[index]} ({occasion.label_en})",
    )


def _relation(
    graph: FamilyGraph, role: CompadrazgoRole, alter: str, link: GodparentLink
) -> CompadrazgoRelation:
    label_es, label_en = _labels(role, graph.sex(alter), link.occasion)
    return CompadrazgoRelation(role, alter, link.occasion, link.godchild, label_es, label_en)


def compadrazgo(
    graph: FamilyGraph,
    godparents: Iterable[GodparentLink],
    ego: str,
    alter: str | None = None,
) -> list[CompadrazgoRelation]:
    """Return every compadrazgo relation of `ego` (only those with `alter`, if given).

    The list is sorted by role, then alter, occasion and godchild, so output is stable.
    """
    found: set[CompadrazgoRelation] = set()
    for link in godparents:
        parents = graph.kin_parents(link.godchild)
        if link.godchild == ego:
            found.add(_relation(graph, CompadrazgoRole.GODPARENT, link.godparent, link))
        if link.godparent == ego:
            found.add(_relation(graph, CompadrazgoRole.GODCHILD, link.godchild, link))
            for parent in parents:
                if parent != ego:
                    found.add(_relation(graph, CompadrazgoRole.COMPADRE, parent, link))
        if ego in parents and link.godparent != ego:
            found.add(_relation(graph, CompadrazgoRole.COMPADRE, link.godparent, link))
    relations = [r for r in found if alter is None or r.alter == alter]
    return sorted(relations, key=lambda r: (r.role, r.alter, r.occasion, r.godchild))
