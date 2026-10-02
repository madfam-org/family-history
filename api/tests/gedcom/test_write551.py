"""GEDCOM 5.5.1 writer: downgrade rules, markings, CONC splitting and re-import."""

from __future__ import annotations

from gedcom_helpers import SEVEN_FIXTURE, dataset, fixture_bytes

from family_history.gedcom import (
    GedcomDocument,
    import_gedcom551,
    parse_gedcom7,
    write_gedcom551,
)
from family_history.gedcom.lines import GEDCOM551


def _export(text: str) -> str:
    return write_gedcom551(parse_gedcom7(text).document).data.decode("utf-8")


def _lines(text: str) -> list[str]:
    return text.splitlines()


def test_fixture_downgrade_shape_and_report() -> None:
    export = write_gedcom551(parse_gedcom7(fixture_bytes(SEVEN_FIXTURE)).document)
    text = export.data.decode("utf-8")
    lines = _lines(text)
    assert "\r\n" in text and not text.startswith("\ufeff")
    assert lines[0] == "0 HEAD" and lines[-1] == "0 TRLR"
    assert {"1 GEDC", "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED", "1 CHAR UTF-8"} <= set(lines)
    assert "1 SCHMA" not in lines
    assert "2 CONT GEDCOM 7.0 extension tags used in this file:" in lines
    assert "1 LANG Spanish" in lines
    # Godparent of a baptism moves to INDI.ASSO with RELA naming the event.
    assert "2 RELA Padrino de bautismo (BAPM 2 APR 1931)" in lines
    # 7.0-only constructs are marked, never dropped.
    for marked in (
        "1 _UID 9b5f8c2e-0000-4000-8000-000000000001",
        "1 _NO MARR",
        "3 _TIME 06:30",
        "2 _SEX X",
        "1 _EXID 4f1e0c2a-synthetic",
        "2 _TITL Foto de la boda",
    ):
        assert marked in lines, marked
    assert "2 DATE INT @#DJULIAN@ 1750 (1750/51 en el libro original)" in lines
    assert "3 _PHRASE entre 1954 y 1956, según la tarjeta de identificación" in lines
    assert "0 @N1@ NOTE Cirilo fue padrino en varias familias del pueblo." in lines
    assert "1 NOTE @N1@" in lines
    assert "1 NOTE @@silverio decía que el río crecía en julio." in lines
    assert "2 FORM jpg" in lines and "3 TYPE photo" in lines
    assert "2 PEDI birth" in lines and "1 RESN confidential" in lines
    assert {d.code for d in export.report} >= {"schema", "marked", "asso-lifted", "sex-x"}


def test_export_is_deterministic_and_reimports_cleanly() -> None:
    doc = parse_gedcom7(fixture_bytes(SEVEN_FIXTURE)).document
    first = write_gedcom551(doc).data
    assert write_gedcom551(doc).data == first
    back = import_gedcom551(first)
    assert {d.code for d in back.report.warnings} <= {"date-upgraded"}
    people = {i.xref: i for i in back.document.individuals}
    assert people["@I2@"].events[0].date is not None
    assert people["@I2@"].events[0].date.phrase == "1750/51 en el libro original"
    assert people["@I1@"].associations[0].role is not None
    # "Padrino de bautismo (BAPM ...)" maps back to GODP by its first word.
    assert people["@I1@"].associations[0].role.value == "GODP"


def test_long_lines_are_split_with_conc_without_edge_spaces() -> None:
    words = " ".join(f"palabra{i}" for i in range(120))
    text = _export(dataset(f"0 @N1@ SNOTE {words}"))
    lines = _lines(text)
    note_lines = [line for line in lines if line.startswith(("0 @N1@", "1 CONC"))]
    assert len(note_lines) > 1
    assert all(len(line) <= 255 for line in lines)
    for line in note_lines[1:]:
        value = line[len("1 CONC ") :]
        assert value and not value.startswith(" ")
    for line in note_lines[:-1]:
        assert not line.endswith(" ")
    back = import_gedcom551(text.encode("utf-8"))
    assert back.document.shared_notes[0].value == words


def test_all_at_signs_are_doubled_except_date_escapes() -> None:
    text = _export(dataset("0 @I1@ INDI\n1 NOTE mail me@x.invalid\n1 BIRT\n2 DATE JULIAN 1700"))
    assert "1 NOTE mail me@@x.invalid" in _lines(text)
    assert "2 DATE @#DJULIAN@ 1700" in _lines(text)
    assert GEDCOM551.escape_all_at_signs


def test_dates_phrases_and_calendars() -> None:
    body = (
        "0 @I1@ INDI\n1 BIRT\n2 DATE\n3 PHRASE año desconocido\n"
        "1 DEAT\n2 DATE 44 BCE\n1 BURI\n2 DATE FRENCH_R 1 VEND 3\n"
        "1 CHR\n2 DATE _MAYA 13 _BAKTUN 5\n3 PHRASE cuenta larga\n"
    )
    lines = _lines(_export(dataset(body)))
    assert "2 DATE (año desconocido)" in lines
    assert "2 DATE 44 B.C." in lines
    assert "2 DATE @#DFRENCH R@ 1 VEND 3" in lines
    assert "2 DATE (cuenta larga)" in lines


def test_enumerations_and_identifiers() -> None:
    body = (
        "0 @I1@ INDI\n1 RESN CONFIDENTIAL, LOCKED\n1 NAME A /B/\n2 TYPE OTHER\n3 PHRASE Nombre "
        "religioso\n1 NAME C /D/\n2 TYPE PROFESSIONAL\n"
        "1 FAMC @F1@\n2 PEDI OTHER\n3 PHRASE crianza\n2 STAT CHALLENGED\n"
        "1 EXID 12AB\n2 TYPE https://gedcom.io/terms/v7/AFN\n"
        "1 EXID 777\n2 TYPE https://gedcom.io/terms/v7/RFN#ABC\n"
        "1 EXID 42\n2 TYPE https://gedcom.io/terms/v7/RIN#APP\n"
        "1 SOUR @S1@\n2 EVEN BIRT\n3 ROLE GODP\n2 EVEN\n"
        "0 @F1@ FAM\n1 ASSO @I1@\n2 ROLE WITN\n1 CHIL @VOID@\n0 @S1@ SOUR\n"
    )
    lines = _lines(_export(dataset(body)))
    for expected in (
        "1 RESN confidential",
        "2 _RESN CONFIDENTIAL, LOCKED",
        "2 TYPE Nombre religioso",
        "2 TYPE professional",
        "2 PEDI crianza",
        "2 STAT challenged",
        "1 AFN 12AB",
        "1 RFN ABC:777",
        "1 RIN 42",
        "3 ROLE (Godparent)",
        "1 _ASSO @I1@",
        "2 RELA Witness",
        "1 _CHIL",
    ):
        assert expected in lines, expected


def test_header_gets_submitter_and_source_when_missing() -> None:
    lines = _lines(write_gedcom551(GedcomDocument()).data.decode("utf-8"))
    assert "1 SOUR FAMILY_HISTORY" in lines
    assert "1 SUBM @FHSUBM@" in lines and "0 @FHSUBM@ SUBM" in lines
    assert lines[-1] == "0 TRLR"


def test_media_file_urls_become_paths() -> None:
    body = (
        "0 @M1@ OBJE\n1 FILE media/boda%201958.jpg\n2 FORM image/jpeg\n3 MEDI OTHER\n4 PHRASE "
        "negativo\n1 FILE file:///C:/Fotos/a%20b.png\n2 FORM image/png\n"
        "1 FILE https://example.invalid/x.mp3\n2 FORM audio/mpeg\n"
        "1 FILE media/unknown.xyz\n2 FORM application/x-thing\n"
    )
    lines = _lines(_export(dataset(body)))
    for expected in (
        "1 FILE media/boda 1958.jpg",
        "3 TYPE negativo",
        "1 FILE C:/Fotos/a b.png",
        "2 FORM png",
        "1 FILE https://example.invalid/x.mp3",
        "2 FORM mp3",
        "2 FORM xyz",
    ):
        assert expected in lines, expected


def test_options() -> None:
    doc = GedcomDocument()
    assert write_gedcom551(doc, bom=True).data.startswith(b"\xef\xbb\xbf0 HEAD")
    assert b"\r" not in write_gedcom551(doc, line_ending="\n").data
    try:
        write_gedcom551(doc, line_ending="x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
