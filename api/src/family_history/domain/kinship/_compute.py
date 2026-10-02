"""Relationship computation: what `alter` is to `ego` in a `FamilyGraph`.

Order of precedence, first match wins:

1. the same person;
2. a partner (a spouse who is also a cousin is called a spouse);
3. kinship by birth or full adoption: breadth-first search up both pedigrees to the lowest
   common ancestor, giving the generation distances `up` (ego to ancestor) and `down`
   (ancestor to alter);
4. explicit foster and step parent-child links;
5. step relations through a partner: padrastro, hijastro, hermanastro;
6. affinity through one partner: suegro, cuñado, yerno, and «<term> político» in general;
7. two-step affinity: concuño (partner's sibling's partner), consuegro (child's parent-in-law).

Labels name `alter` from `ego`'s side and agree with `alter`'s sex.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ._graph import FamilyGraph, PartnerStatus, Pedigree
from ._labels import (
    Terms,
    ancestor_terms,
    cousin_terms,
    descendant_terms,
    nephew_terms,
    sibling_terms,
    terms,
    uncle_terms,
)

__all__ = ["DEFAULT_MAX_DEPTH", "Kinship", "KinshipKind", "kinship"]

DEFAULT_MAX_DEPTH = 8


class KinshipKind(StrEnum):
    SELF = "self"
    PARTNER = "partner"
    BLOOD = "blood"
    FOSTER = "foster"
    STEP = "step"
    IN_LAW = "in_law"


@dataclass(frozen=True, slots=True)
class Kinship:
    """A structured relationship plus its labels.

    `up`/`down` are generation distances of the underlying kinship (for in-laws, of the blood
    link through the partner). `half` is True only when both people's other parents are known
    and differ; None means unknown. `via` names the partner or parent an in-law or step
    relation goes through.
    """

    kind: KinshipKind
    label_es: str
    label_en: str
    up: int = 0
    down: int = 0
    half: bool | None = None
    adoptive: bool = False
    partner_status: PartnerStatus | None = None
    via: str | None = None

    @property
    def in_law(self) -> bool:
        return self.kind is KinshipKind.IN_LAW

    @property
    def step(self) -> bool:
        return self.kind is KinshipKind.STEP


@dataclass(frozen=True, slots=True)
class _Blood:
    up: int
    down: int
    half: bool | None
    adoptive: bool

    @property
    def distance(self) -> int:
        return self.up + self.down


@dataclass(slots=True)
class _Ancestry:
    dist: dict[str, int]
    toward: dict[str, str]
    adoptive: dict[str, bool]


def _ancestry(graph: FamilyGraph, start: str, max_depth: int) -> _Ancestry:
    found = _Ancestry({start: 0}, {}, {start: False})
    frontier = [start]
    for depth in range(1, max_depth + 1):
        following: list[str] = []
        for node in frontier:
            for parent, pedigree in graph.parents(node).items():
                if not pedigree.is_kinship or parent in found.dist:
                    continue
                found.dist[parent] = depth
                found.toward[parent] = node
                found.adoptive[parent] = found.adoptive[node] or pedigree is Pedigree.ADOPTED
                following.append(parent)
        frontier = following
    return found


def _blood(graph: FamilyGraph, ego: str, alter: str, max_depth: int) -> _Blood | None:
    mine, theirs = _ancestry(graph, ego, max_depth), _ancestry(graph, alter, max_depth)
    common = mine.dist.keys() & theirs.dist.keys()
    if not common:
        return None
    lca = min(common, key=lambda c: (mine.dist[c] + theirs.dist[c], mine.dist[c], c))
    up, down = mine.dist[lca], theirs.dist[lca]
    half: bool | None = None
    if up and down:
        mine_parents = graph.kin_parents(mine.toward[lca])
        their_parents = graph.kin_parents(theirs.toward[lca])
        shared = mine_parents & their_parents
        if len(shared) >= 2:
            half = False
        elif len(mine_parents) >= 2 and len(their_parents) >= 2:
            half = True
    return _Blood(up, down, half, mine.adoptive[lca] or theirs.adoptive[lca])


def _blood_terms(blood: _Blood) -> Terms:
    up, down = blood.up, blood.down
    if down == 0:
        if up == 1 and blood.adoptive:
            return terms("padre adoptivo", "madre adoptiva", "adoptive father",
                         "adoptive mother", "adoptive parent",
                         es_n="progenitor/a adoptivo/a")  # fmt: skip
        return ancestor_terms(up)
    if up == 0:
        if down == 1 and blood.adoptive:
            return terms("hijo adoptivo", "hija adoptiva", "adopted son", "adopted daughter",
                         "adopted child")  # fmt: skip
        return descendant_terms(down)
    if up == down == 1:
        return sibling_terms(blood.half is True)
    if up > down:
        return uncle_terms(up, down)
    if down > up:
        return nephew_terms(up, down)
    return cousin_terms(up)


_PARTNER_TERMS: dict[PartnerStatus, Terms] = {
    PartnerStatus.MARRIED: terms("esposo", "esposa", "husband", "wife", "spouse",
                                 es_n="cónyuge"),  # fmt: skip
    PartnerStatus.UNION_LIBRE: terms("pareja", "pareja", "partner", "partner", "partner"),
    PartnerStatus.PARTNER: terms("pareja", "pareja", "partner", "partner", "partner"),
    PartnerStatus.SEPARATED: terms("expareja", "expareja", "former partner", "former partner",
                                   "former partner"),  # fmt: skip
    PartnerStatus.DIVORCED: terms("exesposo", "exesposa", "ex-husband", "ex-wife", "ex-spouse",
                                  es_n="excónyuge"),  # fmt: skip
}

_STEP_PARENT = terms("padrastro", "madrastra", "stepfather", "stepmother", "stepparent")
_STEP_CHILD = terms("hijastro", "hijastra", "stepson", "stepdaughter", "stepchild")
_STEP_SIBLING = terms("hermanastro", "hermanastra", "stepbrother", "stepsister", "stepsibling")
_FOSTER_PARENT = terms("padre de crianza", "madre de crianza", "foster father",
                       "foster mother", "foster parent",
                       es_n="padre/madre de crianza")  # fmt: skip
_FOSTER_CHILD = terms("hijo de crianza", "hija de crianza", "foster son", "foster daughter",
                      "foster child")  # fmt: skip
_PARENT_IN_LAW = terms("suegro", "suegra", "father-in-law", "mother-in-law", "parent-in-law")
_CHILD_IN_LAW = terms("yerno", "nuera", "son-in-law", "daughter-in-law", "child-in-law")
_SIBLING_IN_LAW = terms("cuñado", "cuñada", "brother-in-law", "sister-in-law",
                        "sibling-in-law")  # fmt: skip
_CO_SIBLING_IN_LAW = terms("concuño", "concuña", "co-brother-in-law", "co-sister-in-law",
                           "co-sibling-in-law")  # fmt: skip
_CO_PARENT_IN_LAW = terms("consuegro", "consuegra", "co-father-in-law", "co-mother-in-law",
                          "co-parent-in-law")  # fmt: skip


def _make(
    graph: FamilyGraph,
    alter: str,
    kind: KinshipKind,
    chosen: Terms,
    *,
    up: int = 0,
    down: int = 0,
    half: bool | None = None,
    adoptive: bool = False,
    partner_status: PartnerStatus | None = None,
    via: str | None = None,
) -> Kinship:
    label_es, label_en = chosen.pick(graph.sex(alter))
    return Kinship(kind, label_es, label_en, up, down, half, adoptive, partner_status, via)


def _political(blood_terms: Terms) -> Terms:
    by_marriage = blood_terms.map_es("político", "política")
    return Terms(by_marriage.es_m, by_marriage.es_f, by_marriage.es_n,
                 f"{blood_terms.en_m} by marriage", f"{blood_terms.en_f} by marriage",
                 f"{blood_terms.en_n} by marriage")  # fmt: skip


def kinship(
    graph: FamilyGraph, ego: str, alter: str, max_depth: int = DEFAULT_MAX_DEPTH
) -> Kinship | None:
    """Return what `alter` is to `ego`, or None if unrelated within `max_depth` generations."""
    if max_depth < 1:
        raise ValueError("max_depth must be at least 1")
    if ego == alter:
        return Kinship(KinshipKind.SELF, "la misma persona", "same person")
    status = graph.partners(ego).get(alter)
    if status is not None:
        return _make(graph, alter, KinshipKind.PARTNER, _PARTNER_TERMS[status],
                     partner_status=status)  # fmt: skip
    blood = _blood(graph, ego, alter, max_depth)
    if blood is not None:
        return _make(graph, alter, KinshipKind.BLOOD, _blood_terms(blood), up=blood.up,
                     down=blood.down, half=blood.half, adoptive=blood.adoptive)  # fmt: skip
    return _non_blood(graph, ego, alter, max_depth)


def _non_blood(graph: FamilyGraph, ego: str, alter: str, max_depth: int) -> Kinship | None:
    direct = _direct_link(graph, ego, alter)
    if direct is not None:
        return direct
    step = _step(graph, ego, alter)
    if step is not None:
        return step
    affine = _affinity(graph, ego, alter, max_depth)
    if affine is not None:
        return affine
    return _two_step_affinity(graph, ego, alter)


def _direct_link(graph: FamilyGraph, ego: str, alter: str) -> Kinship | None:
    as_parent = graph.parents(ego).get(alter)
    if as_parent is Pedigree.FOSTER:
        return _make(graph, alter, KinshipKind.FOSTER, _FOSTER_PARENT, up=1)
    if as_parent is Pedigree.STEP:
        return _make(graph, alter, KinshipKind.STEP, _STEP_PARENT, up=1)
    as_child = graph.children(ego).get(alter)
    if as_child is Pedigree.FOSTER:
        return _make(graph, alter, KinshipKind.FOSTER, _FOSTER_CHILD, down=1)
    if as_child is Pedigree.STEP:
        return _make(graph, alter, KinshipKind.STEP, _STEP_CHILD, down=1)
    return None


def _step(graph: FamilyGraph, ego: str, alter: str) -> Kinship | None:
    my_parents = sorted(graph.kin_parents(ego))
    for parent in my_parents:
        if alter in graph.partners(parent):
            return _make(graph, alter, KinshipKind.STEP, _STEP_PARENT, up=1, via=parent)
    for partner in sorted(graph.partners(ego)):
        if partner in graph.kin_parents(alter):
            return _make(graph, alter, KinshipKind.STEP, _STEP_CHILD, down=1, via=partner)
    their_parents = graph.kin_parents(alter)
    for parent in my_parents:
        for other in sorted(their_parents):
            if other in graph.partners(parent):
                return _make(graph, alter, KinshipKind.STEP, _STEP_SIBLING, up=1, down=1,
                             via=parent)  # fmt: skip
    return None


def _affinity(graph: FamilyGraph, ego: str, alter: str, max_depth: int) -> Kinship | None:
    best: tuple[int, int, str, Terms, _Blood] | None = None
    # Alter is a blood relative of ego's partner (suegro, cuñado, «… político»).
    for partner in sorted(graph.partners(ego)):
        blood = _blood(graph, partner, alter, max_depth)
        if blood is None or blood.up == 0:
            continue  # a partner's descendant is a stepchild, handled earlier
        if (blood.up, blood.down) == (1, 0):
            chosen = _PARENT_IN_LAW
        elif (blood.up, blood.down) == (1, 1):
            chosen = _SIBLING_IN_LAW
        else:
            chosen = _political(_blood_terms(blood))
        candidate = (blood.distance, 0, partner, chosen, blood)
        best = candidate if best is None or candidate[:2] < best[:2] else best
    # Alter is the partner of ego's blood relative (yerno, cuñado, «… político»).
    for partner in sorted(graph.partners(alter)):
        blood = _blood(graph, ego, partner, max_depth)
        if blood is None or blood.down == 0:
            continue  # an ancestor's partner is a step-parent, handled earlier
        if (blood.up, blood.down) == (0, 1):
            chosen = _CHILD_IN_LAW
        elif (blood.up, blood.down) == (1, 1):
            chosen = _SIBLING_IN_LAW
        else:
            chosen = _political(_blood_terms(blood))
        candidate = (blood.distance, 1, partner, chosen, blood)
        best = candidate if best is None or candidate[:2] < best[:2] else best
    if best is None:
        return None
    _, _, via, chosen, blood = best
    return _make(graph, alter, KinshipKind.IN_LAW, chosen, up=blood.up, down=blood.down,
                 half=blood.half, adoptive=blood.adoptive, via=via)  # fmt: skip


def _siblings(graph: FamilyGraph, person: str) -> set[str]:
    found: set[str] = set()
    for parent in graph.kin_parents(person):
        found.update(c for c, ped in graph.children(parent).items() if ped.is_kinship)
    found.discard(person)
    return found


def _two_step_affinity(graph: FamilyGraph, ego: str, alter: str) -> Kinship | None:
    alter_partners = set(graph.partners(alter))
    for partner in sorted(graph.partners(ego)):
        if _siblings(graph, partner) & alter_partners:
            return _make(graph, alter, KinshipKind.IN_LAW, _CO_SIBLING_IN_LAW, up=1, down=1,
                         via=partner)  # fmt: skip
    for child, pedigree in sorted(graph.children(ego).items()):
        if not pedigree.is_kinship:
            continue
        for child_partner in sorted(graph.partners(child)):
            if alter in graph.kin_parents(child_partner):
                return _make(graph, alter, KinshipKind.IN_LAW, _CO_PARENT_IN_LAW, via=child)
    return None
