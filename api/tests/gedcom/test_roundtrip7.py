"""parse7 -> write7 -> parse7 is equal, write7 is byte-stable, extensions survive."""

from __future__ import annotations

import pytest

from family_history.gedcom import (
    GedcomDocument,
    Individual,
    Structure,
    import_gedcom551,
    parse_gedcom7,
    write_gedcom7,
    write_gedcom7_text,
)
from family_history.gedcom.extensions import SURNAME_LINE
from family_history.gedcom.model_parts import Event, NamePiece, PersonalName
from gedcom_helpers import SEVEN_FIXTURE, dataset, fixture_bytes

VENDOR_FIXTURES = [
    "ancestry-like-551.ged",
    "myheritage-like-551.ged",
    "gramps-like-551-ansel.ged",
    "rootsmagic-like-551.ged",
]


def test_fixture_round_trip_is_equal_and_byte_stable() -> None:
    first = parse_gedcom7(fixture_bytes(SEVEN_FIXTURE), strict=True)
    written = write_gedcom7(first.document)
    second = parse_gedcom7(written, strict=True)
    assert second.document == first.document
    assert write_gedcom7(second.document) == written
    # Raw structures may be reordered across tags (the spec allows it), but once written they
    # are canonical: a second write of the re-read tree changes nothing.
    assert parse_gedcom7(write_gedcom7(second.document)).structures == second.structures


def test_output_keeps_every_fixture_line() -> None:
    # Substructures of different types may move, but every line is preserved.
    original = fixture_bytes(SEVEN_FIXTURE).decode("utf-8")
    written = write_gedcom7_text(parse_gedcom7(original).document)
    assert written.splitlines()[:6] == original.splitlines()[:6]
    assert sorted(written.splitlines()) == sorted(original.splitlines())


@pytest.mark.parametrize("name", VENDOR_FIXTURES)
def test_upgraded_vendor_files_round_trip(name: str) -> None:
    imported = import_gedcom551(fixture_bytes(name)).document
    written = write_gedcom7(imported)
    reparsed = parse_gedcom7(written)
    assert reparsed.document == imported
    assert write_gedcom7(reparsed.document) == written


def test_bom_and_line_endings() -> None:
    doc = parse_gedcom7(fixture_bytes(SEVEN_FIXTURE)).document
    assert write_gedcom7(doc).startswith(b"\xef\xbb\xbf0 HEAD\n")
    assert write_gedcom7(doc, bom=False).startswith(b"0 HEAD\n")
    crlf = write_gedcom7(doc, line_ending="\r\n")
    assert crlf.count(b"\r\n") == crlf.count(b"\n")
    assert parse_gedcom7(crlf).document == doc
    with pytest.raises(ValueError):
        write_gedcom7(doc, line_ending="\t")


def test_unknown_and_extension_substructures_are_lossless_everywhere() -> None:
    body = (
        "0 @I1@ INDI\n1 NAME Ana /Ruiz/\n2 _NAMEX deep\n3 SURN extension-defined\n4 _MORE x\n"
        "1 BIRT\n2 DATE 1900\n3 _DATEX y\n2 TITL odd standard tag in wrong place\n"
        "1 OCCU Partera\n2 _VERIFIED Y\n1 OCCU Costurera\n"
        "0 @X1@ _CUSTOMREC payload\n1 _CHILD @I1@\n"
    )
    text = dataset(body)
    doc = parse_gedcom7(text).document
    again = parse_gedcom7(write_gedcom7(doc)).document
    assert again == doc
    indi = doc.individuals[0]
    assert indi.names[0].other[0].tag == "_NAMEX"
    assert indi.events[0].date is not None and indi.events[0].date.other[0].tag == "_DATEX"
    assert indi.events[0].other[0].tag == "TITL"
    assert [e.value for e in indi.events if e.tag == "OCCU"] == ["Partera", "Costurera"]
    assert doc.extension_records[0].pointer is None
    assert doc.extension_records[0].payload == "payload"


def test_text_field_with_extension_child_degrades_to_other_in_order() -> None:
    body = "0 @S1@ SOUR\n1 TITL Libro\n2 _ORIG Liber\n1 AUTH Parroquia\n"
    source = parse_gedcom7(dataset(body)).document.sources[0]
    assert source.title is None and source.other[0].tag == "TITL"
    assert source.author == "Parroquia"
    assert parse_gedcom7(write_gedcom7(parse_gedcom7(dataset(body)).document)).document.sources[
        0
    ] == source


def test_schema_is_written_for_madfam_tags_used() -> None:
    piece = NamePiece(value="Hernández", other=[Structure(tag=SURNAME_LINE.tag, payload="PATERNAL")])
    person = Individual(
        xref="@I1@",
        names=[PersonalName(value="Lupe /Hernández/", surnames=[piece])],
        events=[Event(tag="BIRT", value="Y")],
    )
    doc = GedcomDocument(individuals=[person])
    text = write_gedcom7_text(doc)
    assert text.startswith("0 HEAD\n1 GEDC\n2 VERS 7.0\n1 SCHMA\n2 TAG _FH_SURNAME_LINE ")
    assert SURNAME_LINE.uri in text
    assert text.endswith("0 TRLR\n")
    parse_gedcom7(text, strict=True)
    # An existing definition for the same tag wins over ours.
    doc.header = parse_gedcom7(
        "0 HEAD\n1 GEDC\n2 VERS 7.0\n1 SCHMA\n2 TAG _FH_SURNAME_LINE https://other.example\n"
        "0 TRLR\n"
    ).document.header
    assert SURNAME_LINE.uri not in write_gedcom7_text(doc)


def test_empty_document_is_valid_7() -> None:
    text = write_gedcom7_text(GedcomDocument())
    assert text == "0 HEAD\n1 GEDC\n2 VERS 7.0\n0 TRLR\n"
    parse_gedcom7(text, strict=True)


def test_records_are_grouped_in_a_stable_order() -> None:
    body = "0 @S1@ SOUR\n1 TITL t\n0 @F1@ FAM\n0 @I1@ INDI\n0 @U1@ SUBM\n1 NAME n\n"
    text = write_gedcom7_text(parse_gedcom7(dataset(body)).document)
    order = [line.split(" ")[1] for line in text.splitlines() if line.startswith("0 @")]
    assert order == ["@U1@", "@I1@", "@F1@", "@S1@"]
