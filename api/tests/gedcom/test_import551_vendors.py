"""Vendor-shaped synthetic 5.5.1 files import with the expected warnings and data."""

from __future__ import annotations

from gedcom_helpers import UTF8_BOM, fixture_bytes

from family_history.gedcom import import_gedcom551, parse_gedcom7, write_gedcom7
from family_history.gedcom.diagnostics import Severity


def _strictly_valid_except(result_doc: object, allowed: set[str]) -> None:
    """The upgraded document re-read as 7.0 has no violations other than ``allowed``."""
    from family_history.gedcom import GedcomDocument

    assert isinstance(result_doc, GedcomDocument)
    reread = parse_gedcom7(write_gedcom7(result_doc))
    assert {d.code for d in reread.warnings} <= allowed


def test_ancestry_like() -> None:
    result = import_gedcom551(fixture_bytes("ancestry-like-551.ged"))
    report = result.report
    assert report.source_product == "Ancestry.com Family Trees"
    assert report.source_version == "5.5.1"
    assert report.encoding == "utf-8" and report.declared_charset == "UTF-8"
    assert report.record_counts == {
        "FAM": 1,
        "INDI": 3,
        "OBJE": 1,
        "REPO": 1,
        "SOUR": 1,
        "_MTTAG": 1,
    }
    assert report.extension_tags == {"_APID": 2, "_ENV": 1, "_MTTAG": 1, "_TREE": 1}
    codes = report.codes()
    assert codes["date-upgraded"] == 1  # 1750/51
    assert codes["date-normalized"] == 3  # mixed-case months and "abt"
    assert [d.code for d in report.warnings] == ["date-upgraded"]
    doc = result.document
    silverio = doc.individuals[0]
    assert silverio.sex == "M"
    assert silverio.notes[0].value == (
        "Contaba que el río crecía cada julio y que la familia cruzaba por el vado viejo; "
        "su correo era silverio@ejemplo.invalid"
    )
    citation = silverio.events[0].citations[0]
    assert citation.other[0].tag == "_APID"
    teodora = doc.individuals[1]
    birth_date = teodora.events[0].date
    assert birth_date is not None and (birth_date.value, birth_date.phrase) == ("1751", "1750/51")
    media = doc.media[0].files[0]
    assert media.value == "https://example.invalid/synthetic/silverio.jpg"
    assert media.form is not None and media.form.value == "image/jpeg"
    assert media.form.medium is not None and media.form.medium.value == "PHOTO"
    assert doc.extension_records[0].tag == "_MTTAG"
    assert doc.header.source is not None and doc.header.source.other[0].tag == "_TREE"
    _strictly_valid_except(doc, set())


def test_myheritage_like() -> None:
    result = import_gedcom551(fixture_bytes("myheritage-like-551.ged"))
    report = result.report
    assert report.record_counts == {"FAM": 1, "INDI": 3}
    assert report.extension_tags["_UPD"] == 3 and report.extension_tags["_MARNM"] == 1
    assert report.codes()["exid"] == 4
    assert [d.code for d in report.warnings] == ["residual-not-allowed"]
    remedios = result.document.individuals[0]
    assert remedios.other[0].tag == "_UPD"
    assert remedios.names[0].other[0].tag == "_MARNM"
    exid = remedios.external_ids[0]
    assert (exid.value, exid.type) == (
        "MH:I500001",
        "https://gedcom.io/terms/v7/RIN#MYHERITAGE",
    )
    role = remedios.associations[0].role
    assert role is not None and (role.value, role.phrase) == ("GODP", "Madrina")
    pedigree = remedios.child_of[0].pedigree
    assert pedigree is not None and pedigree.value == "ADOPTED"
    xv = remedios.events[1]
    assert (xv.tag, xv.type) == ("EVEN", "XV años")
    assert result.document.header.language == "es"
    # INDI.EMAIL is not 7.0, so it is kept as found and reported as a residual.
    assert [o.tag for o in remedios.other] == ["_UPD", "EMAIL", "_UID"]
    _strictly_valid_except(result.document, {"not-allowed"})


def test_gramps_like_ansel() -> None:
    result = import_gedcom551(fixture_bytes("gramps-like-551-ansel.ged"))
    report = result.report
    assert report.encoding == "ansel" and report.declared_charset == "ANSEL"
    ansel = [d for d in report.diagnostics if d.code == "ansel-replacements"]
    assert ansel and "0xFC x1" in ansel[0].message and ansel[0].severity is Severity.WARNING
    doc = result.document
    jose = doc.individuals[0]
    assert jose.names[0].value == "José Luis /Peña Ávila/"
    assert doc.individuals[1].names[0].value == "Ramón /Navarro/"
    dates = [e.date.value for e in jose.events if e.date is not None]
    assert dates == ["JULIAN 3 MAR 1712", "FRENCH_R 1 VEND 3"]
    assert jose.associations[0].role is not None
    assert jose.associations[0].role.value == "GODP"
    pedigree = jose.child_of[0].pedigree
    assert pedigree is not None and pedigree.value == "FOSTER"
    note = doc.shared_notes[0]
    assert note.value == "Nota con señas: piñón y güero.\nEuro: € y un byte suelto: �"
    file = doc.media[0].files[0]
    assert file.value == "file:///home/demo/fotos/retrato%20abuela.tif"
    assert file.form is not None and file.form.value == "image/tiff"
    assert jose.shared_notes == ["@N0000@"]
    _strictly_valid_except(doc, set())


def test_rootsmagic_like_bom_crlf_and_quirks() -> None:
    data = fixture_bytes("rootsmagic-like-551.ged")
    assert data.startswith(UTF8_BOM) and data.count(UTF8_BOM) == 1  # the importer really sees a BOM
    result = import_gedcom551(data)
    report = result.report
    assert report.encoding == "utf-8"
    assert report.renamed_xrefs == {"@s-1@": "@S_1@"}
    assert report.created_records == {"OBJE": 1, "SOUR": 1}
    codes = report.codes()
    for code in ("xref-renamed", "inline-media", "inline-source", "type-added"):
        assert codes[code] == 1, code
    assert codes["date-upgraded"] == 3
    doc = result.document
    silverio = doc.individuals[0]
    birth = silverio.events[0]
    assert birth.date is not None and birth.date.value == "BET 1930 AND 1931"
    assert birth.citations[0].pointer == "@S_1@"
    baptism = silverio.events[1]
    assert baptism.date is not None
    assert (baptism.date.value, baptism.date.phrase) == ("1931", "poco después de la Semana Santa")
    work = silverio.events[2]
    assert (work.value, work.type) == ("Trabajó en los campos de California", work.value)
    assert work.date is not None and (work.date.value, work.date.phrase) == (
        None,
        "temporada de 1955",
    )
    link = silverio.media[0]
    assert link.pointer == "@FHO1@" and link.title == "Boda de Silverio"
    obje = next(m for m in doc.media if m.xref == "@FHO1@")
    assert obje.files[0].value == "fotos/boda%201958.jpg"
    assert obje.files[0].title == "Boda de Silverio"
    marriage = doc.families[0].events[0]
    created = next(s for s in doc.sources if s.xref == marriage.citations[0].pointer)
    assert created.title == "Acta de matrimonio vista por la familia, sin registro de fuente"
    assert created.text is not None and created.text.value == "Se casaron en la parroquia."
    assert doc.sources[0].xref == "@S_1@"
    _strictly_valid_except(doc, set())


def test_every_vendor_diagnostic_carries_a_line_or_is_file_level() -> None:
    for name in (
        "ancestry-like-551.ged",
        "myheritage-like-551.ged",
        "gramps-like-551-ansel.ged",
        "rootsmagic-like-551.ged",
    ):
        report = import_gedcom551(fixture_bytes(name)).report
        file_level = {"xref-renamed"}
        assert all(d.line is not None or d.code in file_level for d in report.diagnostics), name
