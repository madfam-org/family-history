"""The family graph: people with a sex, parent-child edges with pedigree, partner edges."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "FamilyGraph",
    "ParentLink",
    "PartnerLink",
    "PartnerStatus",
    "Pedigree",
    "Sex",
]


class Sex(StrEnum):
    """Sex as recorded, matching the v1 API: male, female, intersex/other (X), unknown (U)."""

    MALE = "M"
    FEMALE = "F"
    OTHER = "X"
    UNKNOWN = "U"


class Pedigree(StrEnum):
    """How a child is linked to a parent (GEDCOM `PEDI`, minus the LDS-only `SEALING`)."""

    BIRTH = "birth"
    ADOPTED = "adopted"
    FOSTER = "foster"
    STEP = "step"

    @property
    def is_kinship(self) -> bool:
        """Birth and full adoption create kinship (adopción plena); foster and step do not."""
        return self in (Pedigree.BIRTH, Pedigree.ADOPTED)


class PartnerStatus(StrEnum):
    """The state of a couple's union."""

    MARRIED = "married"
    UNION_LIBRE = "union_libre"
    PARTNER = "partner"
    SEPARATED = "separated"
    DIVORCED = "divorced"

    @property
    def is_current(self) -> bool:
        return self not in (PartnerStatus.SEPARATED, PartnerStatus.DIVORCED)


@dataclass(frozen=True, slots=True)
class ParentLink:
    """`parent` is a parent of `child`, linked by `pedigree`."""

    parent: str
    child: str
    pedigree: Pedigree = Pedigree.BIRTH


@dataclass(frozen=True, slots=True)
class PartnerLink:
    """`a` and `b` are (or were) a couple."""

    a: str
    b: str
    status: PartnerStatus = PartnerStatus.MARRIED


class FamilyGraph:
    """An immutable view of a family as a graph (not a tree: pedigree collapse is fine)."""

    def __init__(
        self,
        sexes: Mapping[str, Sex],
        parent_links: Iterable[ParentLink] = (),
        partner_links: Iterable[PartnerLink] = (),
    ) -> None:
        self._sexes = dict(sexes)
        self._parents: dict[str, dict[str, Pedigree]] = {}
        self._children: dict[str, dict[str, Pedigree]] = {}
        self._partners: dict[str, dict[str, PartnerStatus]] = {}
        for link in parent_links:
            if link.parent == link.child:
                raise ValueError(f"{link.parent!r} cannot be their own parent")
            self._parents.setdefault(link.child, {})[link.parent] = link.pedigree
            self._children.setdefault(link.parent, {})[link.child] = link.pedigree
        for union in partner_links:
            if union.a == union.b:
                raise ValueError(f"{union.a!r} cannot partner themselves")
            self._partners.setdefault(union.a, {})[union.b] = union.status
            self._partners.setdefault(union.b, {})[union.a] = union.status

    def sex(self, person: str) -> Sex:
        return self._sexes.get(person, Sex.UNKNOWN)

    def __contains__(self, person: object) -> bool:
        return (
            person in self._sexes
            or person in self._parents
            or person in self._children
            or person in self._partners
        )

    def parents(self, person: str) -> Mapping[str, Pedigree]:
        """All parents of `person` with the pedigree of each link."""
        return self._parents.get(person, {})

    def kin_parents(self, person: str) -> set[str]:
        """Parents linked by birth or adoption."""
        return {p for p, pedigree in self.parents(person).items() if pedigree.is_kinship}

    def children(self, person: str) -> Mapping[str, Pedigree]:
        return self._children.get(person, {})

    def partners(self, person: str) -> Mapping[str, PartnerStatus]:
        return self._partners.get(person, {})
