"""Tokenizer, decoder and level-structure builder."""

from __future__ import annotations

import pytest

from family_history.gedcom.charsets import decode_gedcom7
from family_history.gedcom.diagnostics import Diagnostics, GedcomStrictError, Severity
from family_history.gedcom.lines import (
    GEDCOM7,
    GEDCOM551,
    build_structures,
    split_lines,
    tokenize,
)
from family_history.gedcom.parse7 import parse_gedcom7, read_structures
from gedcom_helpers import dataset


def _roots(text: str, *, strict: bool = False, dialect=GEDCOM7):  # type: ignore[no-untyped-def]
    diagnostics = Diagnostics(strict=strict)
    lines = tokenize(text, diagnostics, dialect)
    return build_structures(lines, diagnostics, dialect), diagnostics


def _codes(diagnostics: Diagnostics) -> list[str]:
    return [d.code for d in diagnostics]


@pytest.mark.parametrize("terminator", ["\n", "\r\n", "\r"])
def test_every_line_terminator_is_accepted(terminator: str) -> None:
    text = terminator.join(["0 HEAD", "1 GEDC", "2 VERS 7.0", "0 TRLR"]) + terminator
    roots, diagnostics = _roots(text, strict=True)
    assert [r.tag for r in roots] == ["HEAD", "TRLR"]
    assert not diagnostics.has_errors


def test_mixed_terminators_and_no_final_terminator() -> None:
    assert split_lines("a\r\nb\rc\nd") == ["a", "b", "c", "d"]
    assert split_lines("a\n") == ["a"]


def test_unicode_line_separators_stay_inside_payloads() -> None:
    roots, diagnostics = _roots("0 @N1@ SNOTE uno\u2028dos\x85tres\n")
    # U+2028 is ordinary text; U+0085 is a banned C1 control and is removed with a report.
    assert roots[0].payload == "uno\u2028dostres"
    assert _codes(diagnostics) == ["banned-character"]


def test_bom_utf8_and_utf16_are_decoded() -> None:
    text = dataset("0 @I1@ INDI\n1 NAME José /Peña/")
    diagnostics = Diagnostics(strict=True)
    decoded = decode_gedcom7(b"\xef\xbb\xbf" + text.encode("utf-8"), diagnostics)
    assert decoded.text.startswith("0 HEAD") and not diagnostics.has_errors
    for bom, codec in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        diagnostics = Diagnostics(strict=False)
        decoded = decode_gedcom7(bom + text.encode(codec), diagnostics)
        assert "José /Peña/" in decoded.text
        assert _codes(diagnostics) == ["not-utf8"]
        assert diagnostics.items[0].severity is Severity.WARNING


def test_invalid_utf8_reports_line_number() -> None:
    data = dataset("0 @I1@ INDI\n1 NAME Bad /\xff/").encode("latin-1")
    result = parse_gedcom7(data)
    bad = [d for d in result.diagnostics if d.code == "invalid-encoding"]
    assert bad and bad[0].line == 5
    with pytest.raises(GedcomStrictError) as caught:
        parse_gedcom7(data, strict=True)
    assert any(d.line == 5 for d in caught.value.diagnostics)


def test_pointer_text_and_escape_rules() -> None:
    roots, diagnostics = _roots(
        "0 @I1@ INDI\n1 FAMC @F1@\n1 NOTE @@me and @I\n2 CONT @@second\n1 ALIA @VOID@\n",
        strict=True,
    )
    indi = roots[0]
    assert indi.xref == "@I1@"
    assert indi.children[0].pointer == "@F1@" and indi.children[0].payload is None
    assert indi.children[1].payload == "@me and @I\n@second"
    assert indi.children[2].pointer == "@VOID@"
    assert not diagnostics.has_errors


def test_single_leading_at_is_a_violation_but_kept() -> None:
    roots, diagnostics = _roots("0 @I1@ INDI\n1 NOTE @#DJULIAN@ 1750\n")
    assert roots[0].children[0].payload == "@#DJULIAN@ 1750"
    assert _codes(diagnostics) == ["line-value-at"]


def test_cont_joins_with_newlines_and_preserves_spaces() -> None:
    roots, _ = _roots("0 @N1@ SNOTE first \n1 CONT\n1 CONT   indented\n")
    # The first space after CONT is the delimiter; the rest belong to the payload.
    assert roots[0].payload == "first \n\n  indented"


def test_conc_is_rejected_in_7_but_joined_and_accepted_in_551() -> None:
    roots, diagnostics = _roots("0 @N1@ SNOTE abc\n1 CONC def\n")
    assert roots[0].payload == "abcdef"
    assert _codes(diagnostics) == ["conc-in-7"]
    roots, diagnostics = _roots("0 @N1@ NOTE abc\n1 CONC def\n", dialect=GEDCOM551)
    assert roots[0].payload == "abcdef" and not diagnostics.items


def test_misplaced_continuation_is_joined_and_reported() -> None:
    roots, diagnostics = _roots("0 @I1@ INDI\n1 NOTE a\n2 LANG es\n2 CONT b\n")
    assert roots[0].children[0].payload == "a\nb"
    assert "continuation-misplaced" in _codes(diagnostics)


def test_continuation_of_pointer_becomes_note() -> None:
    roots, diagnostics = _roots("0 @I1@ INDI\n1 FAMC @F1@\n2 CONT stray\n")
    famc = roots[0].children[0]
    assert famc.pointer == "@F1@" and famc.children[0].tag == "NOTE"
    assert "continuation-of-pointer" in _codes(diagnostics)


def test_level_jump_is_clamped_with_line_number() -> None:
    roots, diagnostics = _roots("0 @I1@ INDI\n1 BIRT\n3 DATE 1900\n")
    assert roots[0].children[0].children[0].tag == "DATE"
    jump = [d for d in diagnostics if d.code == "level-jump"]
    assert jump and jump[0].line == 3


def test_orphan_and_garbage_lines_never_crash() -> None:
    text = "1 NAME orphan\n0 @N1@ SNOTE start\nthis line was wrapped by a broken exporter\n"
    roots, diagnostics = _roots(text)
    assert roots[0].payload == "start\nthis line was wrapped by a broken exporter"
    assert {"orphan-line", "unparseable-line"} <= set(_codes(diagnostics))


def test_blank_and_banned_characters() -> None:
    roots, diagnostics = _roots("0 @N1@ SNOTE a\x07b\n\n0 TRLR\n")
    assert roots[0].payload == "ab"
    assert {"banned-character", "blank-line"} <= set(_codes(diagnostics))


def test_lowercase_tag_xref_on_substructure_and_trailing_space() -> None:
    roots, diagnostics = _roots("0 @I1@ INDI\n1 @X1@ NAME A\n1 sex M\n1 OCCU \n")
    tags = [c.tag for c in roots[0].children]
    assert tags == ["NAME", "SEX", "OCCU"]
    assert roots[0].children[0].xref is None
    assert {"xref-on-substructure", "tag-syntax", "empty-line-value"} <= set(_codes(diagnostics))


def test_leading_whitespace_and_level_leading_zero() -> None:
    roots, diagnostics = _roots("  0 @I1@ INDI\n01 SEX M\n")
    assert roots[0].children[0].tag == "SEX"
    assert {"line-spacing", "level-leading-zero"} <= set(_codes(diagnostics))


def test_void_cannot_be_an_xref_and_bad_xref_syntax() -> None:
    _, diagnostics = _roots("0 @VOID@ INDI\n0 @i-1@ INDI\n")
    assert {"xref-void", "xref-syntax"} <= set(_codes(diagnostics))


def test_depth_limit_is_enforced_without_recursion_errors() -> None:
    lines = ["0 @X1@ _DEEP"] + [f"{level} _DEEP x" for level in range(1, 400)]
    diagnostics = Diagnostics(strict=False)
    roots = read_structures("\n".join(lines), diagnostics, max_depth=50)
    assert "too-deep" in _codes(diagnostics)
    assert sum(1 for _ in roots[0].walk()) == 400


def test_errors_are_warnings_in_tolerant_mode() -> None:
    _, diagnostics = _roots("0 HEAD\n\n0 TRLR\n", strict=False)
    assert all(d.severity is Severity.WARNING for d in diagnostics)
    _, diagnostics = _roots("0 HEAD\n\n0 TRLR\n", strict=True)
    assert all(d.severity is Severity.ERROR for d in diagnostics)
