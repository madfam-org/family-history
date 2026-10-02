"""Individual 5.5.1 -> 7.0 upgrade rules and character-set handling."""

from __future__ import annotations

import pytest

from family_history.gedcom import import_gedcom551
from family_history.gedcom.charsets import decode_gedcom551
from family_history.gedcom.dates551 import upgrade_date
from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.upgrade551_media import media_type_for, to_file_url

HEAD551 = "0 HEAD\n1 SOUR TEST\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


def _import(body: str):  # type: ignore[no-untyped-def]
    return import_gedcom551(HEAD551 + body.rstrip("\n") + "\n0 TRLR\n")


@pytest.mark.parametrize(
    ("original", "value", "phrase", "interpretive"),
    [
        ("12 MAR 1850", "12 MAR 1850", None, False),
        ("@#DJULIAN@ 12 MAR 1750/51", "JULIAN 12 MAR 1751", "@#DJULIAN@ 12 MAR 1750/51", True),
        ("1699/00", "1700", "1699/00", True),
        ("@#DHEBREW@ 1 TSH 5700", "HEBREW 1 TSH 5700", None, False),
        ("@#DFRENCH R@ 1 VEND 3", "FRENCH_R 1 VEND 3", None, False),
        ("@#DGREGORIAN@ 1 JAN 1900", "1 JAN 1900", None, False),
        ("44 B.C.", "44 BCE", None, False),
        ("INT 1850 (about the war)", "1850", "about the war", True),
        ("(unknown)", "", "unknown", True),
        ("Abt. 1850", "ABT 1850", None, False),
        ("circa 1850", "ABT 1850", None, False),
        ("bet. 1850 and 1855", "BET 1850 AND 1855", None, False),
        ("12 marzo 1850", "12 MAR 1850", None, False),
        ("1850-03-12", "12 MAR 1850", None, False),
        ("03 JAN 1900", "3 JAN 1900", None, False),
        ("@#DROMAN@ 12", "", "@#DROMAN@ 12", True),
        ("12/03/1850", "", "12/03/1850", True),
        ("sometime", "", "sometime", True),
        ("", "", None, False),
    ],
)
def test_date_upgrades(original: str, value: str, phrase: str | None, interpretive: bool) -> None:
    result = upgrade_date(original)
    assert (result.value, result.phrase, result.interpretive) == (value, phrase, interpretive)


def test_head_is_rewritten() -> None:
    text = (
        "0 HEAD\n1 SOUR APP\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
        "1 FILE x.ged\n1 LANG Klingon\n1 SUBN @SN@\n0 @SN@ SUBN\n1 TEMP X\n0 TRLR\n"
    )
    result = import_gedcom551(text)
    header = result.document.header
    assert header.version == "7.0" and header.language == "und"
    assert header.gedc is not None and header.gedc.other == []
    assert {"language-unknown", "subn-dropped", "head-dropped"} <= set(result.report.codes())
    assert result.document.extension_records == []


def test_missing_head_version_and_garbage_never_raise() -> None:
    result = import_gedcom551("0 @I1@ INDI\n1 NAME X /Y/\nnot a line\n")
    assert result.document.individuals[0].names[0].value == "X /Y/\nnot a line"
    assert {"missing-head", "unparseable-line"} <= set(result.report.codes())
    assert import_gedcom551(b"\x00\xff\xfe garbage").document is not None
    other = import_gedcom551("0 HEAD\n1 GEDC\n2 VERS 7.0\n0 TRLR\n")
    assert "version" in other.report.codes()


def test_notes_ages_sex_and_enumerations() -> None:
    body = (
        "0 @I1@ INDI\n1 NAME Ana /Ruiz/\n2 TYPE nickname\n1 SEX N\n1 NOTE @N1@\n"
        "1 BIRT\n2 AGE CHILD\n1 DEAT\n2 AGE 27\n1 BURI\n2 AGE about thirty\n"
        "1 RESN privacy\n1 FAMC @F1@\n2 PEDI step\n2 STAT proven\n"
        "0 @F1@ FAM\n0 @N1@ NOTE shared\n"
    )
    result = _import(body)
    indi = result.document.individuals[0]
    assert indi.shared_notes == ["@N1@"]
    assert result.document.shared_notes[0].value == "shared"
    assert indi.sex == "U"
    ages = [e.age for e in indi.events]
    assert [(a.value, a.phrase) for a in ages if a] == [
        ("< 8y", "Child"),
        ("27y", None),
        (None, "about thirty"),
    ]
    assert indi.restriction == "PRIVACY"
    name_type = indi.names[0].type
    assert name_type is not None and (name_type.value, name_type.phrase) == ("AKA", "nickname")
    link = indi.child_of[0]
    assert link.pedigree is not None and (link.pedigree.value, link.pedigree.phrase) == (
        "OTHER",
        "step",
    )
    assert link.status is not None and link.status.value == "PROVEN"
    assert {"sex-unknown", "age-phrase", "enum-mapped"} <= set(result.report.codes())


def test_associations_identifiers_and_citation_roles() -> None:
    body = (
        "0 @I1@ INDI\n1 ASSO @I2@\n2 TYPE INDI\n2 RELA Testigo\n1 ASSO @I2@\n"
        "1 AFN 12AB-3CD\n1 RFN ABC:777\n1 RIN 42\n"
        "1 SOUR @S1@\n2 EVEN BIRT\n3 ROLE (Godmother)\n"
        "0 @I2@ INDI\n0 @S1@ SOUR\n"
    )
    result = _import(body)
    indi = result.document.individuals[0]
    roles = [(a.role.value, a.role.phrase) for a in indi.associations if a.role]
    assert roles == [("WITN", "Testigo"), ("OTHER", None)]
    assert [(x.value, x.type) for x in indi.external_ids] == [
        ("12AB-3CD", "https://gedcom.io/terms/v7/AFN"),
        ("777", "https://gedcom.io/terms/v7/RFN#ABC"),
        ("42", "https://gedcom.io/terms/v7/RIN#TEST"),
    ]
    event = indi.citations[0].event
    assert event is not None and event.role is not None
    assert (event.role.value, event.role.phrase) == ("GODP", "Godmother")
    assert "asso-no-role" in result.report.codes()


def test_events_alias_coordinates_and_xref_collisions() -> None:
    body = (
        "0 @I-1@ INDI\n1 DEAT ahogado en el río\n1 EVEN\n1 ALIA Lupita\n"
        "1 BIRT\n2 PLAC Somewhere\n3 MAP\n4 LATI 19.43\n4 LONG -99.13\n"
        "0 @I_1@ INDI\n1 ASSO @I-1@\n2 RELA amigo\n"
    )
    result = _import(body)
    first, second = result.document.individuals
    assert result.report.renamed_xrefs == {"@I-1@": "@I_1_2@"}
    assert first.xref == "@I_1_2@" and second.associations[0].pointer == "@I_1_2@"
    death = first.events[0]
    assert death.value == "Y" and death.notes[0].value == "ahogado en el río"
    assert first.events[1].type == "Unspecified"
    assert [n.value for n in first.names] == ["Lupita"]
    assert first.names[0].type is not None and first.names[0].type.value == "AKA"
    place = first.events[2].place
    assert place is not None and place.map is not None
    assert (place.map.latitude, place.map.longitude) == ("N19.43", "W99.13")


def test_media_shapes_from_5_5_and_5_5_1() -> None:
    body = (
        "0 @M1@ OBJE\n1 FORM gif\n1 TITL Old style\n1 FILE scans\\acta.gif\n1 BLOB\n2 CONT xx\n"
        "0 @M2@ OBJE\n1 FILE \\\\server\\share\\a b.xyz\n2 FORM xyz\n3 MEDI Microfilm roll\n"
    )
    result = _import(body)
    old, odd = result.document.media
    assert old.files[0].value == "scans/acta.gif"
    assert old.files[0].form is not None and old.files[0].form.value == "image/gif"
    assert old.files[0].title == "Old style"
    file = odd.files[0]
    assert file.value == "file://server/share/a%20b.xyz"
    assert file.form is not None and file.form.value == "application/octet-stream"
    medium = file.form.medium
    assert medium is not None and (medium.value, medium.phrase) == ("OTHER", "Microfilm roll")
    assert {"blob-dropped", "media-type-unknown", "medium-other"} <= set(result.report.codes())


@pytest.mark.parametrize(
    ("path", "url"),
    [
        ("C:\\Fotos\\boda.jpg", "file:///C:/Fotos/boda.jpg"),
        ("/home/a/b c.png", "file:///home/a/b%20c.png"),
        ("media/foto.jpg", "media/foto.jpg"),
        ("https://example.invalid/x y.jpg", "https://example.invalid/x%20y.jpg"),
        ("fotos/100%.jpg", "fotos/100%25.jpg"),
        ("fotos/a%20b.jpg", "fotos/a%20b.jpg"),
        ("fotos/peña.jpg", "fotos/peña.jpg"),
    ],
)
def test_file_paths_become_urls(path: str, url: str) -> None:
    assert to_file_url(path) == url


def test_media_type_lookup() -> None:
    assert media_type_for("JPG", None) == ("image/jpeg", True)
    assert media_type_for(None, "x/y.PDF") == ("application/pdf", True)
    assert media_type_for("image/webp", None) == ("image/webp", True)
    assert media_type_for("zzz", None) == ("application/octet-stream", False)


@pytest.mark.parametrize(
    ("data", "encoding", "code"),
    [
        (
            "0 HEAD\n1 CHAR ANSI\n0 @N1@ NOTE Peña\n".encode("cp1252"),
            "cp1252",
            "charset-nonstandard",
        ),
        ("0 HEAD\n1 CHAR ASCII\n0 @N1@ NOTE Peña\n".encode(), "utf-8", "charset-mismatch"),
        ("0 HEAD\n1 CHAR ANSEL\n0 @N1@ NOTE Peña\n".encode(), "utf-8", "charset-mismatch"),
        ("0 HEAD\n0 @N1@ NOTE Peña\n".encode("cp1252"), "cp1252", "charset-fallback"),
        ("0 HEAD\n1 CHAR UNICODE\n".encode("utf-16"), "utf-16-le", None),
        (b"0 HEAD\n1 CHAR UNICODE\n0 @N1@ NOTE x\n", "utf-8", "charset-mismatch"),
        ("0 HEAD\r1 CHAR IBMPC\r".encode("cp437"), "cp437", "charset-nonstandard"),
        ("0 HEAD\n1 CHAR MACINTOSH\n".encode("mac_roman"), "mac_roman", "charset-nonstandard"),
        (b"0 HEAD\n1 CHAR KLINGON\n", "utf-8", "charset-unknown"),
    ],
)
def test_charsets(data: bytes, encoding: str, code: str | None) -> None:
    diagnostics = Diagnostics(strict=False)
    decoded = decode_gedcom551(data, diagnostics)
    assert decoded.encoding == encoding
    expected = [code] if code else []
    if code == "charset-fallback":
        expected = ["charset-missing", "charset-fallback"]
    assert [d.code for d in diagnostics] == expected
    if b"N1" in data and encoding != "utf-8":
        assert "Peña" in decoded.text or "x" in decoded.text


def test_ansel_round_trip_of_spanish_letters() -> None:
    from family_history.gedcom.ansel import decode_ansel

    result = decode_ansel(b"\xe2a\xe2e\xe2i\xe2o\xe2u \xe4n\xe4N \xe8u \xc5\xc6 \xa5")
    assert result.text == "áéíóú ñÑ ü ¿¡ Æ"
    assert not result.undefined
    dangling = decode_ansel(b"abc\xe2")
    assert dangling.dangling_marks == 1
