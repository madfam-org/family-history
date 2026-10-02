"""Tests for derived godparent and compadre relations."""

from __future__ import annotations

import pytest

from family_history.domain.compadrazgo import (
    CompadrazgoRole,
    GodparentLink,
    Occasion,
    compadrazgo,
)
from family_history.domain.events import EventType
from family_history.domain.kinship import FamilyGraph, ParentLink, Pedigree, Sex

GRAPH = FamilyGraph(
    {
        "papa": Sex.MALE, "mama": Sex.FEMALE, "nina": Sex.FEMALE, "nino": Sex.MALE,
        "padrino": Sex.MALE, "madrina": Sex.FEMALE, "tia": Sex.FEMALE, "neutro": Sex.OTHER,
        "novio": Sex.MALE, "suegro": Sex.MALE, "adoptiva": Sex.FEMALE, "crianza": Sex.MALE,
    },
    [
        ParentLink("papa", "nina"), ParentLink("mama", "nina"),
        ParentLink("papa", "nino"), ParentLink("mama", "nino"),
        ParentLink("suegro", "novio"),
        ParentLink("adoptiva", "nino", Pedigree.ADOPTED),
        ParentLink("crianza", "nina", Pedigree.FOSTER),
    ],
)  # fmt: skip
LINKS = [
    GodparentLink("padrino", "nina", Occasion.BAUTIZO),
    GodparentLink("madrina", "nina", Occasion.BAUTIZO),
    GodparentLink("tia", "nina", Occasion.XV_ANOS),
    GodparentLink("neutro", "nino", Occasion.CONFIRMACION),
    GodparentLink("padrino", "nina", Occasion.BODA),
    GodparentLink("padrino", "novio", Occasion.BODA),
]


def _labels(ego: str, alter: str | None = None) -> list[tuple[str, str, str]]:
    return [(r.alter, r.label_es, r.label_en) for r in compadrazgo(GRAPH, LINKS, ego, alter)]


def test_godchild_sees_godparents() -> None:
    assert _labels("nina") == [
        ("madrina", "madrina de bautizo", "godmother (baptism)"),
        ("padrino", "padrino de bautizo", "godfather (baptism)"),
        ("padrino", "padrino de boda", "godfather (wedding)"),
        ("tia", "madrina de XV años", "godmother (quinceañera)"),
    ]


def test_godparent_sees_godchildren_and_compadres() -> None:
    relations = compadrazgo(GRAPH, LINKS, "padrino")
    by_role = {(r.role, r.alter, r.occasion) for r in relations}
    assert (CompadrazgoRole.GODCHILD, "nina", Occasion.BAUTIZO) in by_role
    assert (CompadrazgoRole.GODCHILD, "novio", Occasion.BODA) in by_role
    assert (CompadrazgoRole.COMPADRE, "papa", Occasion.BAUTIZO) in by_role
    assert (CompadrazgoRole.COMPADRE, "mama", Occasion.BAUTIZO) in by_role
    # Padrinos de boda become compadres of both spouses' parents.
    assert (CompadrazgoRole.COMPADRE, "suegro", Occasion.BODA) in by_role
    labels = {(r.alter, r.label_es) for r in relations if r.role is CompadrazgoRole.COMPADRE}
    assert ("mama", "comadre de bautizo") in labels
    assert ("papa", "compadre de bautizo") in labels


def test_parents_see_compadres() -> None:
    assert _labels("mama", "madrina") == [
        ("madrina", "comadre de bautizo", "comadre (baptism)"),
    ]
    assert _labels("papa", "neutro") == [
        ("neutro", "compadre/comadre de confirmación", "compadre/comadre (confirmation)"),
    ]


def test_adoptive_parents_are_compadres_but_foster_parents_are_not() -> None:
    assert [r.label_es for r in compadrazgo(GRAPH, LINKS, "adoptiva")] == [
        "compadre/comadre de confirmación"
    ]
    assert compadrazgo(GRAPH, LINKS, "crianza") == []


def test_neutral_godchild_and_godparent_labels() -> None:
    graph = FamilyGraph({"g": Sex.UNKNOWN, "c": Sex.OTHER}, [])
    links = [GodparentLink("g", "c", Occasion.PRIMERA_COMUNION)]
    (as_child,) = compadrazgo(graph, links, "c")
    (as_godparent,) = compadrazgo(graph, links, "g")
    assert as_child.label_es == "padrino/madrina de primera comunión"
    assert as_godparent.label_es == "ahijado/a de primera comunión"
    assert as_godparent.label_en == "godchild (first communion)"


def test_unrelated_and_validation() -> None:
    assert _labels("papa", "tia") == [("tia", "comadre de XV años", "comadre (quinceañera)")]
    assert compadrazgo(GRAPH, LINKS, "papa", "suegro") == []
    assert compadrazgo(GRAPH, LINKS, "nadie") == []
    with pytest.raises(ValueError, match="own godparent"):
        GodparentLink("x", "x", Occasion.BAUTIZO)


def test_parent_who_is_also_godparent_is_not_their_own_compadre() -> None:
    links = [GodparentLink("papa", "nina", Occasion.PRESENTACION)]
    roles = {(r.role, r.alter) for r in compadrazgo(GRAPH, links, "papa")}
    assert roles == {(CompadrazgoRole.GODCHILD, "nina"), (CompadrazgoRole.COMPADRE, "mama")}


def test_occasions_map_to_events_and_labels() -> None:
    assert Occasion.BAUTIZO.event_type is EventType.BAPTISM
    assert Occasion.BODA.event_type is EventType.RELIGIOUS_MARRIAGE
    assert Occasion.XV_ANOS.event_type is EventType.QUINCEANERA
    for occasion in Occasion:
        assert occasion.label_es and occasion.label_en


def test_output_is_deterministic() -> None:
    assert compadrazgo(GRAPH, LINKS, "padrino") == compadrazgo(GRAPH, list(reversed(LINKS)),
                                                               "padrino")  # fmt: skip
