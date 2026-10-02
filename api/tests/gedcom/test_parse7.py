"""GEDCOM 7.0 reader: strict violations, tolerant warnings and the typed model."""

from __future__ import annotations

import pytest
from gedcom_helpers import SEVEN_FIXTURE, dataset, fixture_bytes

from family_history.gedcom import GedcomStrictError, parse_gedcom7
from family_history.gedcom.diagnostics import Severity
from family_history.gedcom.spec import RECORD_TYPES, STRUCTURE_TYPES


def _violations(text: str) -> list[str]:
    with pytest.raises(GedcomStrictError) as caught:
        parse_gedcom7(text, strict=True)
    return [d.code for d in caught.value.diagnostics if d.severity is Severity.ERROR]


def test_spec_tables_cover_every_record_and_core_structures() -> None:
    assert set(RECORD_TYPES) == {"HEAD", "INDI", "FAM", "OBJE", "REPO", "SNOTE", "SOUR", "SUBM"}
    assert len(STRUCTURE_TYPES) > 150
    name = STRUCTURE_TYPES["g7:INDI-NAME"]
    assert {"GIVN", "SURN", "NICK", "TRAN", "TYPE"} <= set(name.children)
    assert STRUCTURE_TYPES["g7:FAM-EVEN"].children["TYPE"].required


def test_fixture_parses_strictly_into_the_typed_model() -> None:
    result = parse_gedcom7(fixture_bytes(SEVEN_FIXTURE), strict=True)
    doc = result.document
    assert doc.header.version == "7.0"
    assert (
        doc.header.extension_definitions()["_LOC"] == "https://example.org/synthetic/LocationRecord"
    )
    assert [i.xref for i in doc.individuals] == ["@I1@", "@I2@", "@I3@", "@I4@"]
    silverio = doc.individuals[0]
    name = silverio.names[0]
    assert name.value == "Silverio /Cortés Moreno/"
    assert [p.value for p in name.surnames] == ["Cortés", "Moreno"]
    assert [p.value for p in name.nicknames] == ["Chava"]
    assert name.type is not None and name.type.value == "BIRTH"
    birth = silverio.events[0]
    assert birth.tag == "BIRT" and birth.date is not None
    assert (birth.date.value, birth.date.time) == ("12 MAR 1931", "06:30")
    assert birth.place is not None and birth.place.map is not None
    assert birth.place.map.latitude == "N18.6812"
    assert birth.citations[0].page == "Libro 4, foja 12, partida 33"
    baptism = silverio.events[1]
    role = baptism.associations[0].role
    assert role is not None and (role.value, role.phrase) == ("GODP", "Padrino de bautismo")
    assert baptism.other[0].tag == "_FH_SENSITIVITY"
    assert (
        silverio.notes[0].value == "@silverio decía que el río crecía en julio.\n\n  Segunda "
        "línea con espacios iniciales."
    )
    remedios = doc.individuals[2]
    assert remedios.sex == "X"
    assert remedios.child_of[0].pedigree is not None
    assert remedios.child_of[0].pedigree.value == "BIRTH"
    assert remedios.events[1].associations[0].pointer == "@VOID@"
    assert remedios.non_events[0].value == "MARR"
    family = doc.families[0]
    assert family.husband is not None and family.husband.pointer == "@I1@"
    assert [e.type for e in family.events] == ["Matrimonio religioso", "Matrimonio civil"]
    assert doc.media[0].files[0].form is not None
    assert doc.media[0].files[0].form.value == "image/jpeg"
    assert doc.shared_notes[0].value.startswith("Cirilo")
    assert doc.extension_records[0].tag == "_LOC"
    assert result.extension_tags["_FH_SENSITIVITY"] == 3
    assert any(d.code == "undocumented-extensions" for d in result.diagnostics)
    assert doc.by_xref()["@F1@"] is family


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("0 @I1@ INDI\n1 SEX Z", "payload-syntax"),
        ("0 @I1@ INDI\n1 RESN SECRET", "payload-syntax"),
        (
            "0 @I1@ INDI\n1 RESN CONFIDENTIAL, LOCKED, PRIVACY\n1 NAME A /B/\n2 TYPE NICK",
            "payload-syntax",
        ),
        ("0 @I1@ INDI\n1 FAMC @F1@\n2 PEDI NATURAL\n0 @F1@ FAM", "payload-syntax"),
        ("0 @I1@ INDI\n1 SOUR @S1@\n2 QUAY 5\n0 @S1@ SOUR", "payload-syntax"),
        ("0 @I1@ INDI\n1 ASSO @I1@\n2 ROLE PADRINO", "payload-syntax"),
        ("0 @I1@ INDI\n1 BIRT\n2 DATE Abt. 1850", "payload-syntax"),
        ("0 @I1@ INDI\n1 BIRT\n2 DATE 1750/51", "payload-syntax"),
        ("0 @I1@ INDI\n1 BIRT\n2 AGE 27", "payload-syntax"),
        ("0 @I1@ INDI\n1 BIRT\n2 DATE 1 JAN 1900\n3 TIME 25:00", "payload-syntax"),
        ("0 @I1@ INDI\n1 BIRT Yes", "payload-y"),
        ("0 @I1@ INDI\n1 FAMC @F9@", "dangling-pointer"),
        ("0 @I1@ INDI\n1 FAMC @I1@", "pointer-type"),
        ("0 @I1@ INDI\n1 FAMC F1", "expected-pointer"),
        ("0 @I1@ INDI\n1 SEX M\n1 SEX F", "too-many"),
        ("0 @I1@ INDI\n1 EVEN\n2 DATE 1900", "missing-substructure"),
        ("0 @I1@ INDI\n1 CHIL @I1@", "not-allowed"),
        ("0 @I1@ INDI\n0 @I1@ INDI", "duplicate-xref"),
        ("0 @X1@ PLACE\n1 NAME x", "unknown-record"),
        ("0 @N1@ NOTE text", "unknown-record"),
        ("0 @I1@ INDI\n1 NAME A\n2 SURN B\n3 CONC C", "conc-in-7"),
    ],
)
def test_strict_mode_reports_spec_violations(body: str, code: str) -> None:
    assert code in _violations(dataset(body))


def test_shape_violations() -> None:
    assert "missing-trlr" in _violations("0 HEAD\n1 GEDC\n2 VERS 7.0\n")
    assert "missing-head" in _violations("0 @I1@ INDI\n0 TRLR\n")
    assert "gedc-version" in _violations("0 HEAD\n1 GEDC\n2 VERS 5.5.1\n0 TRLR\n")
    assert "after-trlr" in _violations(dataset("") + "0 @I1@ INDI\n")
    schema = (
        "0 HEAD\n1 GEDC\n2 VERS 7.0\n1 SCHMA\n2 TAG _A https://a.example\n"
        "2 TAG _A https://b.example\n0 TRLR\n"
    )
    assert "schema-duplicate" in _violations(schema)


def test_strict_error_lists_every_violation_with_lines() -> None:
    with pytest.raises(GedcomStrictError) as caught:
        parse_gedcom7(dataset("0 @I1@ INDI\n1 SEX Z\n1 FAMC @F9@"), strict=True)
    lines = {(d.code, d.line) for d in caught.value.diagnostics}
    assert {("payload-syntax", 5), ("dangling-pointer", 6)} <= lines
    assert "2 specification violation(s)" in str(caught.value)


def test_valid_7_0_constructs_pass_strict() -> None:
    body = (
        "0 @I1@ INDI\n1 RESN CONFIDENTIAL, LOCKED\n"
        "1 NAME Ana /Ruiz/\n2 TYPE OTHER\n3 PHRASE Apodo\n"
        "1 BIRT\n2 DATE FROM JULIAN 1700 TO GREGORIAN 1701\n2 AGE > 1y 2m\n3 PHRASE poco más\n"
        "1 DEAT\n2 DATE\n3 PHRASE 5 de enero, año desconocido\n"
        "1 EVEN Algo\n2 TYPE Cruce fronterizo\n2 SDATE 1950\n"
        "1 ASSO @VOID@\n2 ROLE _CUSTOM\n1 SEX _OTRO\n"
        "1 _UNKNOWN\n2 NAME extension-defined substructures are not validated\n3 FOO bar\n"
    )
    parse_gedcom7(dataset(body), strict=True)


def test_tolerant_mode_keeps_everything_and_reports_warnings() -> None:
    text = dataset("0 @I1@ INDI\n1 SEX Z\n1 WEIRD thing\n2 _X y\n1 FAMC @F9@")
    result = parse_gedcom7(text)
    indi = result.document.individuals[0]
    assert indi.sex == "Z"
    assert [o.tag for o in indi.other] == ["WEIRD"]
    assert indi.child_of[0].pointer == "@F9@"
    assert {d.code for d in result.warnings} == {
        "payload-syntax",
        "not-allowed",
        "dangling-pointer",
    }
    assert all(d.severity is Severity.WARNING for d in result.warnings)


def test_bytes_and_text_inputs_agree() -> None:
    data = fixture_bytes(SEVEN_FIXTURE)
    assert parse_gedcom7(data).document == parse_gedcom7(data.decode("utf-8-sig")).document
