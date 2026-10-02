"""Property tests: the tokenizer never crashes, and emit -> tokenize -> build is the identity."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.emit import GEDCOM7_EMIT, GEDCOM551_EMIT, emit_lines, render
from family_history.gedcom.lines import BANNED_RE, GEDCOM7, GEDCOM551, build_structures, tokenize
from family_history.gedcom.structure import Structure

_TAGS = st.sampled_from(["NAME", "NOTE", "TEXT", "PLAC", "_EXT", "_FH_X", "TITL", "PAGE"])
_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\r"),
    max_size=40,
).map(lambda s: BANNED_RE.sub("", s))
_POINTER = st.from_regex(r"@[A-Z0-9_]{1,6}@", fullmatch=True)


def _clean_payload(text: str) -> str | None:
    # Empty and missing payloads are equivalent in GEDCOM; a lone empty first line is None.
    return text or None


@st.composite
def structures(draw: st.DrawFn, depth: int = 0) -> Structure:
    tag = draw(_TAGS)
    node = Structure(tag=tag)
    if draw(st.booleans()):
        node.pointer = draw(_POINTER)
    else:
        node.payload = _clean_payload(draw(_TEXT))
    if depth < 3:
        node.children = draw(st.lists(structures(depth + 1), max_size=3))
    return node


@st.composite
def records(draw: st.DrawFn) -> list[Structure]:
    roots = []
    for index, child_list in enumerate(draw(st.lists(st.lists(structures(), max_size=3),
                                                     min_size=1, max_size=3))):
        roots.append(Structure(tag="_REC", xref=f"@R{index}@", children=child_list))
    return roots


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=300))
def test_tokenizer_never_crashes_on_arbitrary_text(text: str) -> None:
    for dialect in (GEDCOM7, GEDCOM551):
        diagnostics = Diagnostics(strict=False)
        roots = build_structures(tokenize(text, diagnostics, dialect), diagnostics, dialect)
        assert all(root.tag for root in roots)


@settings(max_examples=150, deadline=None)
@given(st.binary(max_size=300))
def test_parsers_never_crash_on_arbitrary_bytes(data: bytes) -> None:
    from family_history.gedcom import import_gedcom551, parse_gedcom7

    parse_gedcom7(data)
    import_gedcom551(data)


def _normalize(node: Structure) -> Structure:
    clone = node.copy()
    for item in clone.walk():
        if item.payload is not None and "\n" not in item.payload and item.payload == "":
            item.payload = None
    return clone


@settings(max_examples=200, deadline=None)
@given(records())
def test_emit_then_read_is_identity_in_7(roots: list[Structure]) -> None:
    text = render(emit_lines(roots, GEDCOM7_EMIT))
    diagnostics = Diagnostics(strict=True)
    back = build_structures(tokenize(text, diagnostics, GEDCOM7), diagnostics, GEDCOM7)
    assert not diagnostics.has_errors, list(diagnostics)
    assert back == [_normalize(r) for r in roots]


@settings(max_examples=200, deadline=None)
@given(records())
def test_emit_then_read_is_identity_in_551_with_conc(roots: list[Structure]) -> None:
    for node in (n for r in roots for n in r.walk()):
        if node.payload:
            node.payload = node.payload * 9  # long enough to need CONC splitting
    lines = emit_lines(roots, GEDCOM551_EMIT)
    assert all(len(line) <= 255 for line in lines)
    diagnostics = Diagnostics(strict=False)
    back = build_structures(tokenize(render(lines), diagnostics, GEDCOM551), diagnostics,
                            GEDCOM551)
    assert back == [_normalize(r) for r in roots]
