"""Tests for kinship computation and labels on a synthetic multi-generation family."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from family_history.domain.kinship import (
    FamilyGraph,
    KinshipKind,
    ParentLink,
    PartnerLink,
    PartnerStatus,
    Pedigree,
    Sex,
    kinship,
    merge_es,
    ordinal_en,
    ordinal_es,
)

M, F, X, U = Sex.MALE, Sex.FEMALE, Sex.OTHER, Sex.UNKNOWN

SEXES: dict[str, Sex] = {
    "ap": M, "am": F, "a": M, "b": F, "a2": F, "n": M, "o": F,
    "c": M, "cw": F, "c2": F, "d": F, "dh": M, "e": M, "ew": F,
    "g": M, "gw": F, "h": X, "hh": M, "i": F, "j": M, "j2": M, "j3": F,
    "k": M, "l": F, "l2": U, "m1": M, "p": F, "xx": M, "q": M, "y": M,
    "r": F, "z": M, "s": F, "sp": M, "t": M, "gwf": M, "gwm": F, "lonely": F,
}  # fmt: skip


def _kids(parents: tuple[str, ...], *children: str, pedigree: Pedigree = Pedigree.BIRTH) -> list[
    ParentLink
]:
    return [ParentLink(p, c, pedigree) for p in parents for c in children]


PARENTS = [
    *_kids(("ap", "am"), "a", "a2"),
    *_kids(("a2",), "n"),
    *_kids(("n",), "o"),
    *_kids(("a", "b"), "c", "d", "e"),
    *_kids(("c", "cw"), "g", "h"),
    *_kids(("c", "c2"), "hh"),
    *_kids(("c2", "y"), "q"),
    *_kids(("cw", "xx"), "p"),
    *_kids(("d", "dh"), "i"),
    *_kids(("i",), "m1"),
    *_kids(("e", "ew"), "j"),
    *_kids(("e", "ew"), "r", pedigree=Pedigree.ADOPTED),
    *_kids(("d",), "z", pedigree=Pedigree.FOSTER),
    *_kids(("j",), "j2"),
    *_kids(("j2",), "j3"),
    *_kids(("g", "gw"), "k"),
    *_kids(("k",), "l"),
    *_kids(("l",), "l2"),
    *_kids(("sp",), "cw", "s"),
    *_kids(("gwf", "gwm"), "gw"),
]
PARTNERS = [
    PartnerLink("ap", "am"),
    PartnerLink("a", "b"),
    PartnerLink("c", "cw"),
    PartnerLink("c", "c2", PartnerStatus.SEPARATED),
    PartnerLink("d", "dh", PartnerStatus.UNION_LIBRE),
    PartnerLink("e", "ew"),
    PartnerLink("g", "gw"),
    PartnerLink("s", "t"),
    PartnerLink("gwf", "gwm", PartnerStatus.DIVORCED),
]
GRAPH = FamilyGraph(SEXES, PARENTS, PARTNERS)


@pytest.mark.parametrize(
    ("ego", "alter", "es", "en"),
    [
        ("g", "c", "padre", "father"),
        ("g", "cw", "madre", "mother"),
        ("c", "g", "hijo", "son"),
        ("c", "h", "hijo/a", "child"),
        ("g", "h", "hermano/a", "sibling"),
        ("h", "g", "hermano", "brother"),
        ("g", "hh", "medio hermano", "half-brother"),
        ("g", "p", "media hermana", "half-sister"),
        ("g", "a", "abuelo", "grandfather"),
        ("g", "b", "abuela", "grandmother"),
        ("k", "a", "bisabuelo", "great-grandfather"),
        ("k", "ap", "tatarabuelo", "great-great-grandfather"),
        ("l", "am", "trastatarabuela", "3rd great-grandmother"),
        ("l2", "ap", "quinto abuelo", "4th great-grandfather"),
        ("ap", "l2", "quinto/a nieto/a", "4th great-grandchild"),
        ("a", "g", "nieto", "grandson"),
        ("a", "k", "bisnieto", "great-grandson"),
        ("ap", "k", "tataranieto", "great-great-grandson"),
        ("am", "l", "trastataranieta", "3rd great-granddaughter"),
        ("g", "e", "tío", "uncle"),
        ("g", "d", "tía", "aunt"),
        ("k", "e", "tío abuelo", "great-uncle"),
        ("k", "a2", "tía bisabuela", "great-great-aunt"),
        ("e", "g", "sobrino", "nephew"),
        ("e", "k", "sobrino nieto", "great-nephew"),
        ("g", "j", "primo hermano", "first cousin"),
        ("g", "i", "prima hermana", "first cousin"),
        ("k", "j2", "primo segundo", "second cousin"),
        ("l", "j3", "prima tercera", "third cousin"),
        ("k", "j", "tío segundo", "first cousin once removed"),
        ("j", "k", "sobrino segundo", "first cousin once removed"),
        ("k", "n", "tío abuelo segundo", "first cousin twice removed"),
        ("l", "j2", "tío tercero", "second cousin once removed"),
        ("c", "cw", "esposa", "wife"),
        ("d", "dh", "pareja", "partner"),
        ("c", "c2", "expareja", "former partner"),
        ("gwf", "gwm", "exesposa", "ex-wife"),
        ("cw", "a", "suegro", "father-in-law"),
        ("g", "gwm", "suegra", "mother-in-law"),
        ("a", "cw", "nuera", "daughter-in-law"),
        ("gwm", "g", "yerno", "son-in-law"),
        ("c", "s", "cuñada", "sister-in-law"),
        ("cw", "e", "cuñado", "brother-in-law"),
        ("e", "cw", "cuñada", "sister-in-law"),
        ("c", "t", "concuño", "co-brother-in-law"),
        ("c", "gwf", "consuegro", "co-father-in-law"),
        ("cw", "gwm", "consuegra", "co-mother-in-law"),
        ("g", "ew", "tía política", "aunt by marriage"),
        ("gw", "a", "abuelo político", "grandfather by marriage"),
        ("ew", "g", "sobrino político", "nephew by marriage"),
        ("hh", "cw", "madrastra", "stepmother"),
        ("p", "c", "padrastro", "stepfather"),
        ("cw", "hh", "hijastro", "stepson"),
        ("g", "q", "hermanastro", "stepbrother"),
        ("e", "r", "hija adoptiva", "adopted daughter"),
        ("r", "ew", "madre adoptiva", "adoptive mother"),
        ("g", "r", "prima hermana", "first cousin"),
        ("d", "z", "hijo de crianza", "foster son"),
        ("z", "d", "madre de crianza", "foster mother"),
        ("g", "g", "la misma persona", "same person"),
    ],
)
def test_labels(ego: str, alter: str, es: str, en: str) -> None:
    result = kinship(GRAPH, ego, alter)
    assert result is not None
    assert (result.label_es, result.label_en) == (es, en)


def test_structure_of_cousin_and_half_relations() -> None:
    cousin = kinship(GRAPH, "k", "j")
    assert cousin is not None
    assert (cousin.kind, cousin.up, cousin.down) == (KinshipKind.BLOOD, 3, 2)
    half = kinship(GRAPH, "g", "hh")
    assert half is not None and half.half is True
    full = kinship(GRAPH, "g", "h")
    assert full is not None and full.half is False
    unknown = kinship(GRAPH, "c", "e")  # siblings with both parents known
    assert unknown is not None and unknown.half is False
    adopted = kinship(GRAPH, "g", "r")
    assert adopted is not None and adopted.adoptive


def test_half_is_unknown_when_a_parent_is_missing() -> None:
    graph = FamilyGraph({"p1": M, "x": F, "y": M}, [*_kids(("p1",), "x", "y")])
    result = kinship(graph, "x", "y")
    assert result is not None
    assert result.half is None
    assert result.label_es == "hermano"


def test_in_law_and_step_structure() -> None:
    in_law = kinship(GRAPH, "g", "ew")
    assert in_law is not None and in_law.in_law and in_law.via == "e"
    assert (in_law.up, in_law.down) == (2, 1)
    suegro = kinship(GRAPH, "cw", "a")
    assert suegro is not None and suegro.via == "c"
    step = kinship(GRAPH, "hh", "cw")
    assert step is not None and step.step and step.via == "c"
    spouse = kinship(GRAPH, "c", "c2")
    assert spouse is not None and spouse.partner_status is PartnerStatus.SEPARATED


def test_partner_takes_precedence_over_blood() -> None:
    graph = FamilyGraph(
        {"gp": M, "p1": M, "p2": F, "x": M, "y": F},
        [*_kids(("gp",), "p1", "p2"), *_kids(("p1",), "x"), *_kids(("p2",), "y")],
        [PartnerLink("x", "y")],
    )
    result = kinship(graph, "x", "y")
    assert result is not None and result.label_es == "esposa"


def test_explicit_step_pedigree() -> None:
    graph = FamilyGraph({"s": M, "k": F}, [ParentLink("s", "k", Pedigree.STEP)])
    up = kinship(graph, "k", "s")
    down = kinship(graph, "s", "k")
    assert up is not None and up.label_es == "padrastro"
    assert down is not None and down.label_es == "hijastra"


@pytest.mark.parametrize(
    ("ego", "alter", "es", "en"),
    [
        ("a", "l2", "trastataranieto/a", "3rd great-grandchild"),
        ("b", "l", "tataranieta", "great-great-granddaughter"),
        ("l", "l2", "hijo/a", "child"),
        ("l2", "l", "madre", "mother"),
    ],
)
def test_neutral_labels(ego: str, alter: str, es: str, en: str) -> None:
    result = kinship(GRAPH, ego, alter, max_depth=10)
    assert result is not None
    assert (result.label_es, result.label_en) == (es, en)


def test_neutral_parent_and_spouse_words() -> None:
    graph = FamilyGraph(
        {"p": X, "k": F, "s": U},
        [ParentLink("p", "k")],
        [PartnerLink("k", "s"), PartnerLink("p", "q", PartnerStatus.DIVORCED)],
    )
    parent = kinship(graph, "k", "p")
    spouse = kinship(graph, "k", "s")
    ex = kinship(graph, "p", "q")
    assert parent is not None and (parent.label_es, parent.label_en) == ("progenitor/a", "parent")
    assert spouse is not None and (spouse.label_es, spouse.label_en) == ("cónyuge", "spouse")
    assert ex is not None and ex.label_es == "excónyuge"


def test_unrelated_and_depth_limit() -> None:
    assert kinship(GRAPH, "g", "lonely") is None
    assert kinship(GRAPH, "g", "nobody-in-graph") is None
    assert kinship(GRAPH, "l2", "ap", max_depth=5) is None
    assert kinship(GRAPH, "l2", "ap", max_depth=6) is not None
    with pytest.raises(ValueError, match="max_depth"):
        kinship(GRAPH, "g", "c", max_depth=0)


def test_graph_validation_and_membership() -> None:
    with pytest.raises(ValueError, match="own parent"):
        FamilyGraph({}, [ParentLink("x", "x")])
    with pytest.raises(ValueError, match="partner themselves"):
        FamilyGraph({}, [], [PartnerLink("x", "x")])
    assert "g" in GRAPH and "nobody" not in GRAPH
    assert GRAPH.sex("nobody") is Sex.UNKNOWN


def test_label_helpers() -> None:
    assert merge_es("tío abuelo segundo", "tía abuela segunda") == "tío/a abuelo/a segundo/a"
    assert merge_es("yerno", "nuera") == "yerno/nuera"
    assert merge_es("padre de crianza", "madre") == "padre de crianza/madre"
    assert ordinal_es(3) == "tercero" and ordinal_es(3, feminine=True) == "tercera"
    assert ordinal_es(12) == "12.º" and ordinal_es(12, feminine=True) == "12.ª"
    assert [ordinal_en(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st",
    ]  # fmt: skip


def _chain(length: int) -> FamilyGraph:
    people = {f"p{i}": (M if i % 2 else F) for i in range(length + 1)}
    links = [ParentLink(f"p{i + 1}", f"p{i}") for i in range(length)]
    return FamilyGraph(people, links)


@given(st.integers(1, 14))
def test_direct_line_distances_are_symmetric(generations: int) -> None:
    graph = _chain(generations)
    up = kinship(graph, "p0", f"p{generations}", max_depth=20)
    down = kinship(graph, f"p{generations}", "p0", max_depth=20)
    assert up is not None and down is not None
    assert (up.up, up.down) == (generations, 0)
    assert (down.up, down.down) == (0, generations)
    assert up.label_es and down.label_en


@given(st.integers(1, 6), st.integers(1, 6))
def test_collateral_distances_mirror(left: int, right: int) -> None:
    """Two lines from one couple: the relation one way mirrors the other way."""
    people = {"top1": M, "top2": F}
    links: list[ParentLink] = []
    for side, depth in (("l", left), ("r", right)):
        previous = None
        for level in range(1, depth + 1):
            person = f"{side}{level}"
            people[person] = M
            parents = ("top1", "top2") if previous is None else (previous,)
            links.extend(ParentLink(p, person) for p in parents)
            previous = person
    graph = FamilyGraph(people, links)
    there = kinship(graph, f"l{left}", f"r{right}", max_depth=10)
    back = kinship(graph, f"r{right}", f"l{left}", max_depth=10)
    assert there is not None and back is not None
    assert (there.up, there.down) == (back.down, back.up) == (left, right)
    if left == right:
        assert there.label_es == back.label_es
