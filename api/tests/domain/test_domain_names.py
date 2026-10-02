"""Tests for the Mexican name model, search normalization and hipocorísticos."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from family_history.domain.names import (
    HYPOCORISTICS,
    DisplayStyle,
    NameForm,
    NameType,
    SurnameOrder,
    display_name,
    given_name_variants,
    normalize_for_search,
)

MARIA = NameForm(
    given_names=("María de Jesús",),
    apellido_paterno="López",
    apellido_materno="Hernández",
    nombre_usado="Jesús",
    apodos=("Chuy",),
)
IGNACIO = NameForm(
    given_names=("Ignacio",),
    apellido_paterno="Garza",
    apellido_materno="Treviño",
    particle_paterno="de la",
    surname_joiner="y",
)


@pytest.mark.parametrize(
    ("form", "style", "expected"),
    [
        (MARIA, DisplayStyle.FULL, "María de Jesús «Chuy» López Hernández"),
        (MARIA, DisplayStyle.FORMAL, "María de Jesús López Hernández"),
        (MARIA, DisplayStyle.SHORT, "Jesús López"),
        (MARIA, DisplayStyle.SORTING, "López Hernández, María de Jesús"),
        (IGNACIO, DisplayStyle.FULL, "Ignacio de la Garza y Treviño"),
        (IGNACIO, DisplayStyle.SHORT, "Ignacio de la Garza"),
        (IGNACIO, DisplayStyle.SORTING, "Garza y Treviño, Ignacio de la"),
    ],
)
def test_display_styles(form: NameForm, style: DisplayStyle, expected: str) -> None:
    assert display_name(form, style) == expected


def test_compound_given_names() -> None:
    form = NameForm(given_names=("José", "María"), apellido_paterno="Ruiz")
    assert form.nombre_de_pila == "José María"
    assert display_name(form, DisplayStyle.SHORT) == "José Ruiz"


def test_materno_first_order_scjn() -> None:
    form = NameForm(
        ("Ana",), "López", "Hernández", surname_order=SurnameOrder.MATERNO_FIRST
    )
    assert display_name(form) == "Ana Hernández López"
    assert display_name(form, DisplayStyle.SHORT) == "Ana Hernández"
    assert display_name(form, DisplayStyle.SORTING) == "Hernández López, Ana"
    assert form.sort_surname() == "Hernández"


def test_brazilian_order() -> None:
    form = NameForm(("João",), "Silva", "Souza", surname_order=SurnameOrder.PT_BR, lang="pt-BR")
    assert display_name(form) == "João Souza Silva"
    assert display_name(form, DisplayStyle.SHORT) == "João Silva"
    assert display_name(form, DisplayStyle.SORTING) == "Silva, João Souza"
    assert form.sort_surname() == "Silva"


def test_hyphen_joiner_and_extra_surnames() -> None:
    form = NameForm(
        ("Luis",), "Pérez", "Gómez", surname_joiner="-", extra_surnames=("Ortiz",)
    )
    assert display_name(form) == "Luis Pérez-Gómez Ortiz"
    assert display_name(form, DisplayStyle.SORTING) == "Pérez-Gómez Ortiz, Luis"


def test_partial_names() -> None:
    only_materno = NameForm(("Rosa",), apellido_materno="Díaz")
    assert display_name(only_materno, DisplayStyle.SORTING) == "Díaz, Rosa"
    assert only_materno.sort_surname() == "Díaz"
    only_apodo = NameForm(apodos=("La Güera",))
    assert display_name(only_apodo, DisplayStyle.SHORT) == "La Güera"
    assert display_name(only_apodo, DisplayStyle.SORTING) == "La Güera"
    only_given = NameForm(("Tomasa",))
    assert display_name(only_given, DisplayStyle.SORTING) == "Tomasa"
    assert only_given.sort_surname() == ""
    assert NameForm(extra_surnames=("Ortiz",)).sort_surname() == "Ortiz"


def test_women_keep_their_surnames() -> None:
    """No API derives a married name; the default form is the birth name, unchanged."""
    form = NameForm(("Carmen",), "Ruiz", "Luna")
    assert form.name_type is NameType.BIRTH
    assert display_name(form) == "Carmen Ruiz Luna"
    married = NameForm(("Carmen",), "Ruiz", "Luna", name_type=NameType.MARRIED)
    assert display_name(married) == "Carmen Ruiz Luna"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "at least one"),
        ({"given_names": (" ",)}, "blank"),
        ({"apellido_paterno": " "}, "non-blank"),
        ({"given_names": ("Ana",), "particle_paterno": "von"}, "needs its surname"),
        ({"apellido_paterno": "Garza", "particle_paterno": "xyz"}, "not a known particle"),
        ({"apellido_paterno": "Garza", "surname_joiner": "and"}, "joiner"),
        ({"apellido_paterno": "Garza", "lang": "es_MX"}, "BCP 47"),
    ],
)
def test_validation(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        NameForm(**kwargs)  # type: ignore[arg-type]


def test_indigenous_language_form() -> None:
    form = NameForm(("Xóchitl",), name_type=NameType.INDIGENOUS, lang="nah")
    assert form.name_type.label_es == "Nombre en lengua indígena"
    assert form.name_type.gedcom_type == ("OTHER", "Nombre en lengua indígena")


def test_name_type_gedcom_mapping_and_labels() -> None:
    assert NameType.BIRTH.gedcom_type == ("BIRTH", None)
    assert NameType.MARRIED.gedcom_type == ("MARRIED", None)
    assert NameType.BAPTISM.gedcom_type == ("OTHER", "Nombre de bautizo")
    for name_type in NameType:
        assert name_type.label_es and name_type.label_en


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Ximena", "Jimena"),
        ("Xavier", "Javier"),
        ("Mexía", "Mejía"),
        ("Hernández", "Ernández"),
        ("Vázquez", "Vásquez"),
        ("Velázquez", "Velasques"),
        ("Bárbara", "Várbara"),
        ("Cecilia", "Sesilia"),
        ("Zamora", "Samora"),
        ("Godoy", "Godoi"),
        ("Giménez", "Jiménez"),
        ("Carla", "Karla"),
        ("Castillo", "Castiyo"),
        ("Pérez y González", "Perez Gonzalez"),
        ("Ma. de Jesús", "María de Jesús"),
        ("Gpe. Ortiz", "Guadalupe Ortiz"),
        ("Fco. Ruiz", "Francisco Ruiz"),
        ("  MARÍA   josé ", "maria jose"),
        ("Peña", "Pena"),
    ],
)
def test_search_folds_variants(left: str, right: str) -> None:
    assert normalize_for_search(left) == normalize_for_search(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("J. López", "José López"),  # initials are never expanded
        ("Ma Wei", "María Wei"),  # bare «Ma» without a period is a surname
        ("Chávez", "Cavez"),  # «ch» is kept apart from c
        ("Guerrero", "Jerrero"),  # «gue» keeps its hard g
    ],
)
def test_search_does_not_over_fold(left: str, right: str) -> None:
    assert normalize_for_search(left) != normalize_for_search(right)


def test_search_key_examples() -> None:
    assert normalize_for_search("Ximena Mexía Vázquez") == "jimena mejia baskes"
    assert normalize_for_search("") == ""
    assert normalize_for_search("Ma.de Jesús") == "maria de jesus"


@given(st.text(max_size=60))
def test_normalization_is_idempotent(text: str) -> None:
    once = normalize_for_search(text)
    assert normalize_for_search(once) == once


_NAME_CHARS = st.sampled_from(list("abcdefghijklmnñopqrstuvwxyzáéíóúüABCDEHJMXZ .'-"))


@given(st.text(alphabet=_NAME_CHARS, max_size=40))
def test_normalization_output_is_plain_ascii_words(text: str) -> None:
    key = normalize_for_search(text)
    assert key == " ".join(key.split())
    assert all(ch.isascii() and (ch.isalnum() or ch == " ") for ch in key)


@given(st.text(alphabet=_NAME_CHARS, max_size=40))
def test_normalization_ignores_case_and_accents(text: str) -> None:
    assert normalize_for_search(text.upper()) == normalize_for_search(text.lower())


@pytest.mark.parametrize(
    ("short", "formal"),
    [
        ("Chucho", "jesus"), ("Chuy", "jesus"), ("Pepe", "jose"), ("Pancho", "francisco"),
        ("Paco", "francisco"), ("Lupe", "guadalupe"), ("Lupita", "guadalupe"),
        ("Chabela", "isabel"), ("Chava", "salvador"), ("Nacho", "ignacio"),
        ("Chema", "jose maria"), ("Concha", "concepcion"), ("Conchita", "concepcion"),
        ("Lola", "dolores"), ("Memo", "guillermo"), ("Beto", "alberto"), ("Beto", "roberto"),
        ("Beto", "humberto"), ("Toño", "antonio"), ("Lalo", "eduardo"), ("Quique", "enrique"),
        ("Chayo", "rosario"), ("Charo", "rosario"), ("Cuca", "refugio"),
        ("Cuquita", "refugio"), ("Licha", "alicia"), ("Meche", "mercedes"), ("Pili", "pilar"),
        ("Goyo", "gregorio"), ("Pepa", "josefa"), ("Tere", "teresa"), ("Lencho", "lorenzo"),
        ("Chelo", "consuelo"), ("Toña", "antonia"), ("Nando", "fernando"), ("Rafa", "rafael"),
    ],
)  # fmt: skip
def test_hypocoristics_are_bidirectional(short: str, formal: str) -> None:
    assert formal in given_name_variants(short)
    assert normalize_for_search(short).replace(" ", "") in {
        normalize_for_search(v).replace(" ", "") for v in given_name_variants(formal)
    }


def test_variants_are_accent_and_case_insensitive() -> None:
    assert given_name_variants("JESÚS") == given_name_variants("jesus")
    assert given_name_variants("  José   María ") == {"jose maria", "chema"}
    assert given_name_variants("Alberto") == {"alberto", "beto"}
    assert "roberto" not in given_name_variants("Alberto")
    assert given_name_variants("Zenaida") == {"zenaida"}
    assert given_name_variants("  ") == set()


def test_hypocoristic_map_is_read_only_and_accent_free() -> None:
    with pytest.raises(TypeError):
        HYPOCORISTICS["nuevo"] = ("x",)  # type: ignore[index]
    for formal, shorts in HYPOCORISTICS.items():
        for word in (formal, *shorts):
            assert word.isascii() and word == word.lower()
