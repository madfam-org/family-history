"""Mexican mappings: two surnames, apodos, padrinos, unions, Mexican events, sensitivity."""

from __future__ import annotations

import pytest

from family_history.gedcom import GedcomDocument, Structure, parse_gedcom7, write_gedcom7_text
from family_history.gedcom.mexico import (
    EventKind,
    Godparent,
    MexicanName,
    Sacrament,
    Sensitivity,
    SurnameOrder,
    apply_sensitivity,
    default_sensitivity,
    event_kind,
    event_structure,
    godparents_from_event,
    name_from_structure,
    name_to_structure,
    sacrament_event,
    sensitivity_of,
    union_kind,
)
from family_history.gedcom.model import Family, Individual


def _valid_in_document(indi_children: list[Structure], fam_children: list[Structure]) -> None:
    """The structures are accepted by the strict 7.0 reader inside a real document."""
    indi = Individual.from_structure(Structure(tag="INDI", xref="@I1@", children=indi_children))
    godparent = Individual(xref="@I2@")
    fam = Family.from_structure(Structure(tag="FAM", xref="@F1@", children=fam_children))
    text = write_gedcom7_text(GedcomDocument(individuals=[indi, godparent], families=[fam]))
    parse_gedcom7(text, strict=True)


def test_two_surnames_round_trip_with_extensions() -> None:
    name = MexicanName(
        given="María Guadalupe",
        paternal_surname="Hernández",
        maternal_surname="López",
        nicknames=("Lupita",),
    )
    node = name_to_structure(name)
    assert node.payload == "María Guadalupe /Hernández López/"
    assert [(c.tag, c.payload) for c in node.children] == [
        ("GIVN", "María Guadalupe"),
        ("NICK", "Lupita"),
        ("SURN", "Hernández"),
        ("SURN", "López"),
        ("_FH_SURNAME_ORDER", "PATERNAL_FIRST"),
    ]
    assert node.children[2].text("_FH_SURNAME_LINE") == "PATERNAL"
    assert name_from_structure(node) == name


def test_maternal_first_order_and_prefix_suffix_type() -> None:
    name = MexicanName(
        given="Ana",
        paternal_surname="Smith",
        maternal_surname="García",
        order=SurnameOrder.MATERNAL_FIRST,
        prefix="Dra.",
        suffix="Jr.",
        name_type="BIRTH",
    )
    node = name_to_structure(name)
    assert node.payload == "Dra. Ana /García Smith/ Jr."
    assert name_from_structure(node) == name


def test_reading_names_without_extensions() -> None:
    pieces = Structure(tag="NAME", payload="José /Peña Ibáñez/")
    pieces.add("SURN", "Peña")
    pieces.add("SURN", "Ibáñez")
    read = name_from_structure(pieces)
    assert (read.given, read.paternal_surname, read.maternal_surname) == (
        "José",
        "Peña",
        "Ibáñez",
    )
    bare = name_from_structure(Structure(tag="NAME", payload="Ramón /Núñez Ortiz/"))
    assert (bare.paternal_surname, bare.maternal_surname) == ("Núñez", "Ortiz")
    compound = name_from_structure(Structure(tag="NAME", payload="Juan /de la Garza/"))
    assert (compound.paternal_surname, compound.maternal_surname) == ("de la Garza", None)
    single = name_from_structure(Structure(tag="NAME", payload="Cipriano"))
    assert (single.given, single.paternal_surname) == ("Cipriano", None)


def test_slash_in_name_parts_is_rejected() -> None:
    with pytest.raises(ValueError):
        name_to_structure(MexicanName(given="A/B"))


def test_baptism_with_padrinos_and_religion_class() -> None:
    node = sacrament_event(
        Sacrament.BAPTISM,
        date="2 APR 1931",
        place="Parroquia de San Isidro, Tlacotepec, Puebla, México",
        godparents=[Godparent("@I2@", "Padrino de bautismo"), Godparent(phrase="Madrina")],
    )
    assert node.tag == "BAPM"
    assert sensitivity_of(node) == {Sensitivity.RELIGION}
    assert node.first("RESN") is None
    assert godparents_from_event(node) == [
        Godparent("@I2@", "Padrino de bautismo"),
        Godparent("@VOID@", "Madrina"),
    ]
    living = sacrament_event(Sacrament.CONFIRMATION, subject_living=True)
    assert living.tag == "CONF" and living.text("RESN") == "CONFIDENTIAL"
    assert sacrament_event(Sacrament.FIRST_COMMUNION).tag == "FCOM"
    _valid_in_document([node, living], [])


def test_unions() -> None:
    civil = event_structure(EventKind.CIVIL_MARRIAGE, date="1 AUG 1958")
    religious = sacrament_event(
        Sacrament.RELIGIOUS_MARRIAGE, date="15 AUG 1958", godparents=[Godparent("@I2@", "arras")]
    )
    free = event_structure(EventKind.FREE_UNION, date="FROM 1960")
    assert (civil.tag, civil.text("TYPE")) == ("MARR", "Matrimonio civil")
    assert (religious.tag, religious.text("TYPE")) == ("MARR", "Matrimonio religioso")
    assert (free.tag, free.text("TYPE")) == ("EVEN", "Unión libre")
    assert [union_kind(n) for n in (civil, religious, free)] == [
        EventKind.CIVIL_MARRIAGE,
        EventKind.RELIGIOUS_MARRIAGE,
        EventKind.FREE_UNION,
    ]
    assert sensitivity_of(religious) == {Sensitivity.RELIGION}
    assert sensitivity_of(civil) == frozenset()
    _valid_in_document([], [civil, religious, free])


@pytest.mark.parametrize(
    ("tag", "type_text", "kind"),
    [
        ("MARR", "Religious", EventKind.RELIGIOUS_MARRIAGE),
        ("MARR", "por lo civil", None),
        ("MARR", "Civil", EventKind.CIVIL_MARRIAGE),
        ("MARR", "XV años", None),
        ("EVEN", "Unión libre", EventKind.FREE_UNION),
        ("EVEN", "XV AÑOS", EventKind.QUINCEANERA),
        ("EVEN", "Quinceañera", EventKind.QUINCEANERA),
        ("EVEN", "Programa Bracero", EventKind.BRACERO_CONTRACT),
        ("EVEN", "Border crossing", EventKind.BORDER_CROSSING),
        ("EVEN", "Graduación", None),
    ],
)
def test_kinds_are_recognized_from_type_text(
    tag: str, type_text: str, kind: EventKind | None
) -> None:
    node = Structure(tag=tag)
    node.add("TYPE", type_text)
    assert event_kind(node) == kind


def test_mexican_events_use_even_with_type_and_kind() -> None:
    for kind, label in (
        (EventKind.QUINCEANERA, "XV años"),
        (EventKind.BRACERO_CONTRACT, "Contrato bracero"),
        (EventKind.BORDER_CROSSING, "Cruce fronterizo"),
    ):
        node = event_structure(kind, date="1955", place="Ciudad Juárez, Chihuahua, México")
        assert (node.tag, node.text("TYPE"), node.text("_FH_EVENT_KIND")) == (
            "EVEN",
            label,
            kind.value,
        )
        assert event_kind(node) is kind
        assert union_kind(node) is None
    custom = event_structure(EventKind.BORDER_CROSSING, label="Cruce por Nogales")
    assert custom.text("TYPE") == "Cruce por Nogales" and event_kind(custom) is (
        EventKind.BORDER_CROSSING
    )
    _valid_in_document([custom], [])


def test_sensitivity_merges_and_adds_resn_only_where_permitted() -> None:
    death = Structure(tag="DEAT", payload="Y")
    cause = death.add("CAUS", "Tuberculosis")
    assert default_sensitivity(cause) == {Sensitivity.HEALTH}
    assert default_sensitivity(Structure(tag="BAPM")) == {Sensitivity.RELIGION}
    assert default_sensitivity(Structure(tag="OCCU", payload="Partera")) == frozenset()
    marked_cause = apply_sensitivity(cause, {Sensitivity.HEALTH}, subject_living=True)
    assert marked_cause.first("RESN") is None
    assert marked_cause.text("_FH_SENSITIVITY") == "HEALTH"
    event = Structure(tag="RELI", payload="Católica")
    event.add("RESN", "LOCKED")
    once = apply_sensitivity(event, {Sensitivity.RELIGION}, subject_living=True)
    twice = apply_sensitivity(once, {Sensitivity.POLITICAL}, subject_living=True)
    assert twice.text("RESN") == "LOCKED, CONFIDENTIAL"
    assert twice.text("_FH_SENSITIVITY") == "POLITICAL, RELIGION"
    assert sensitivity_of(twice) == {Sensitivity.POLITICAL, Sensitivity.RELIGION}
    assert event.text("_FH_SENSITIVITY") is None  # the input is not modified
    assert apply_sensitivity(event, (), subject_living=True) == event
    death.children[0] = marked_cause
    _valid_in_document([death, twice], [])
