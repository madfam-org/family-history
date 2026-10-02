"""Tests for the deterministic synthetic family generator."""

from __future__ import annotations

import ast
import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from family_history.domain.compadrazgo import CompadrazgoRole, compadrazgo
from family_history.domain.events import AssociationRole, EventType
from family_history.domain.kinship import KinshipKind, PartnerStatus, Sex, kinship
from family_history.domain.living import LivingStatus, is_private_by_default
from family_history.domain.names import NameType
from family_history.domain.synth import (
    DEFAULT_TODAY,
    SyntheticFamily,
    generate_family,
    synthetic_lexicon,
)

FAMILIES = [generate_family(seed, generations) for seed in range(6) for generations in (3, 4, 5, 6)]


def _check_invariants(family: SyntheticFamily) -> None:
    people = {p.id: p for p in family.people}
    places = {p.id for p in family.places}
    sources = {s.id for s in family.sources}
    citations = {c.id: c for c in family.citations}
    events = {e.id: e for e in family.events}
    lexicon = synthetic_lexicon()
    assert len(people) == len(family.people)
    for person in family.people:
        assert lexicon.covers(person.names[0]) and person.names[0].name_type is NameType.BIRTH
        assert all(lexicon.covers(form) for form in person.names)
    for place in family.places:
        assert lexicon.covers_place(place.name)
        assert place.parent_id is None or place.parent_id in places
        assert place.fictional == (place.kind not in ("country", "state"))
    for citation in family.citations:
        assert citation.source_id in sources
    births: dict[str, dt.date] = {}
    for event in family.events:
        assert all(pid in people for pid in event.principals)
        assert event.place_id is None or event.place_id in places
        assert all(cid in citations for cid in event.citation_ids)
        lo, hi = event.date.jdn_bounds(approx_years=0)
        assert hi is None or event.date.bounds(0).latest is None or (
            event.date.bounds(0).latest <= family.today  # type: ignore[operator]
        )
        assert lo is not None
        if event.event_type is EventType.BIRTH:
            births[event.principals[0]] = event.date.bounds(0).earliest  # type: ignore[assignment]
    for event in family.events:
        if event.event_type is EventType.BIRTH:
            continue
        earliest = event.date.bounds(0).earliest
        assert earliest is not None
        for pid in event.principals:
            assert earliest >= births[pid], (event, pid)
    for association in family.associations:
        assert association.event_id in events and association.person_id in people
        assert association.person_id not in events[association.event_id].principals
    graph_people = set(people)
    for link in family.parent_links:
        assert {link.parent, link.child} <= graph_people
    for union in family.partner_links:
        assert {union.a, union.b} <= graph_people


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f"seed{f.seed}-{len(f.people)}p")
def test_referential_integrity_and_lexicon(family: SyntheticFamily) -> None:
    _check_invariants(family)


def test_is_deterministic() -> None:
    assert generate_family(42, 5) == generate_family(42, 5)
    assert generate_family(42, 5) != generate_family(43, 5)
    assert generate_family(42, 5, today=dt.date(2030, 1, 1)) != generate_family(42, 5)


def test_rejects_out_of_range_generations() -> None:
    for generations in (2, 7):
        with pytest.raises(ValueError, match="between 3 and 6"):
            generate_family(1, generations)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f"seed{f.seed}-{len(f.people)}p")
def test_dual_surnames_pass_down(family: SyntheticFamily) -> None:
    people = {p.id: p for p in family.people}
    parents: dict[str, list[str]] = {}
    for link in family.parent_links:
        parents.setdefault(link.child, []).append(link.parent)
    for child_id, parent_ids in parents.items():
        father = next(people[p] for p in parent_ids if people[p].sex is Sex.MALE)
        mother = next(people[p] for p in parent_ids if people[p].sex is Sex.FEMALE)
        name = people[child_id].names[0]
        assert name.apellido_paterno == father.names[0].apellido_paterno
        assert name.particle_paterno == father.names[0].particle_paterno
        assert name.apellido_materno == mother.names[0].apellido_paterno


@pytest.mark.parametrize("seed", range(6))
def test_generations_and_living_structure(seed: int) -> None:
    family = generate_family(seed, 6)
    by_generation: dict[int, list[str]] = {}
    for person in family.people:
        by_generation.setdefault(person.generation, []).append(person.id)
    assert set(by_generation) == set(range(6))
    oldest = [family.living_status(pid) for pid in by_generation[0]]
    youngest = [family.living_status(pid) for pid in by_generation[5]]
    assert all(not is_private_by_default(status) for status in oldest)
    assert all(status is LivingStatus.LIVING for status in youngest)


def test_deceased_people_have_evidence() -> None:
    for family in FAMILIES:
        for person in family.people:
            if family.living_status(person.id) is LivingStatus.DECEASED:
                assert any(
                    e.event_type.is_death_evidence and e.citation_ids
                    for e in family.events_of(person.id)
                )


def test_variety_across_seeds() -> None:
    counts: Counter[str] = Counter()
    statuses: Counter[PartnerStatus] = Counter()
    for family in FAMILIES:
        counts.update(event.event_type.value for event in family.events)
        statuses.update(link.status for link in family.partner_links)
        counts.update(a.role.value for a in family.associations)
        counts.update(f"name_{f.name_type}" for p in family.people for f in p.names)
        counts.update(e.date.kind.value for e in family.events)
        counts.update("cause" for e in family.events if e.cause)
    for needed in (
        "birth", "baptism", "confirmation", "first_communion", "civil_marriage",
        "religious_marriage", "death", "burial", "bracero_contract", "border_crossing",
        "immigration", "residence", "occupation", "education", "quinceanera", "GODP", "WITN",
        "name_married", "ABT", "FROM", "FROM_TO", "BET", "cause",
    ):  # fmt: skip
        assert counts[needed] > 0, needed
    assert statuses[PartnerStatus.MARRIED] and statuses[PartnerStatus.UNION_LIBRE]


def test_bracero_contracts_fall_in_program_years() -> None:
    for family in FAMILIES:
        for event in family.events:
            if event.event_type is EventType.BRACERO_CONTRACT:
                year = event.date.first.year  # type: ignore[union-attr]
                assert 1942 <= year <= 1964


def test_union_libre_has_no_marriage_events() -> None:
    for family in FAMILIES:
        marriage_couples = {
            frozenset(e.principals)
            for e in family.events
            if e.event_type in (EventType.CIVIL_MARRIAGE, EventType.RELIGIOUS_MARRIAGE)
        }
        for link in family.partner_links:
            couple = frozenset((link.a, link.b))
            if link.status is PartnerStatus.UNION_LIBRE:
                assert couple not in marriage_couples


def test_kinship_and_compadrazgo_on_generated_family() -> None:
    family = generate_family(3, 5)
    graph = family.graph()
    founder = family.people[0]
    descendants = [p for p in family.people if p.generation == 2 and graph.kin_parents(p.id)]
    assert descendants
    relation = kinship(graph, descendants[0].id, founder.id)
    assert relation is not None and relation.kind is KinshipKind.BLOOD
    assert relation.label_es in ("abuelo", "abuela")
    links = family.godparent_links()
    assert links
    godchild_parents = [
        (link, parent) for link in links for parent in graph.kin_parents(link.godchild)
    ]
    link, parent = godchild_parents[0]
    roles = {r.role for r in compadrazgo(graph, links, parent, link.godparent)}
    assert CompadrazgoRole.COMPADRE in roles


def test_sensitivity_of_generated_events() -> None:
    family = generate_family(1, 4)
    baptisms = [e for e in family.events if e.event_type is EventType.BAPTISM]
    assert baptisms and all(e.sensitivity.value == "religion" for e in baptisms)


def test_godparent_associations_carry_occasions() -> None:
    for family in FAMILIES:
        for association in family.associations:
            if association.role is AssociationRole.GODPARENT:
                assert association.occasion is not None
            else:
                assert association.occasion is None


def test_person_lookup() -> None:
    family = generate_family(2, 3)
    first = family.people[0]
    assert family.person(first.id) is first
    with pytest.raises(KeyError):
        family.person("I9999")


def test_lexicon_accessor() -> None:
    lexicon = synthetic_lexicon()
    assert "María de Jesús" in lexicon.given_names and "Jesús" in lexicon.given_names
    assert "Hernández" in lexicon.surnames and "Garza" in lexicon.surnames
    assert "Toño" in lexicon.nicknames
    assert "Jalisco" in lexicon.place_names and "Villa Imaginaria" in lexicon.place_names
    assert not lexicon.covers_place("Guadalajara")
    assert DEFAULT_TODAY == dt.date(2026, 10, 1)
    form = synthetic_lexicon().covers
    family = generate_family(0, 3)
    assert form(family.people[0].names[0])


@settings(max_examples=25, deadline=None)
@given(st.integers(min_value=0, max_value=2**32), st.integers(min_value=3, max_value=6))
def test_any_seed_produces_a_consistent_family(seed: int, generations: int) -> None:
    family = generate_family(seed, generations)
    _check_invariants(family)
    assert max(p.generation for p in family.people) == generations - 1


def _flatten(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return {s for item in value.values() for s in _flatten(item)}
    if isinstance(value, Iterable):
        return {s for item in value for s in _flatten(item)}
    raise TypeError(type(value))


def test_lexicon_is_walkable_as_nested_strings() -> None:
    """The fixture guard walks mappings and iterables of strings; the lexicon is one."""
    lexicon = synthetic_lexicon()
    assert isinstance(lexicon, Mapping)
    flat = _flatten(lexicon)
    assert {"Hernández", "Jesús", "Chuy", "Villa Imaginaria", "Castiyo"} <= flat
    with pytest.raises(KeyError):
        lexicon["unknown"]


_NAME_WORD = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñüã]+\b")
# Capitalised words in these test files that are not names: labels, months, a weekday, and the
# record abbreviations «Fco.» and «Gpe.» (of lexicon names Francisco and Guadalupe).
_NOT_NAMES = {"Nombre", "Fco", "Gpe", "Cristo", "Gregorian", "Lunes", "March", "Marzo"}


@pytest.mark.parametrize(
    "test_file",
    [
        "test_domain_names.py",
        "test_domain_dates_user_input.py",
        "test_domain_kinship.py",
        "test_domain_compadrazgo.py",
    ],
)
def test_name_fixtures_in_tests_come_from_the_lexicon(test_file: str) -> None:
    flat = _flatten(synthetic_lexicon())
    tree = ast.parse((Path(__file__).parent / test_file).read_text(encoding="utf-8"))
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    for node in ast.walk(tree):
        if id(node) in docstrings:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for word in _NAME_WORD.findall(node.value):
                if word in _NOT_NAMES:
                    continue
                assert word in flat, (test_file, word)

