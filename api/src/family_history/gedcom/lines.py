"""Tokenizer and level-structure builder for GEDCOM line streams.

This module turns text into `Structure` trees. It knows the line grammar of both FamilySearch
GEDCOM 7.0 and GEDCOM 5.5.1 (selected by a `Dialect`) but nothing about what the tags mean.

* Line terminators CR, LF and CR-LF are all accepted, mixed or not.
* Errors carry 1-based line numbers. Nothing here raises on malformed input: every problem is
  recorded in a `Diagnostics` collector with error severity when it violates the dialect's
  grammar, and the line is repaired or set aside so reading can continue. Strict callers turn
  those errors into an exception afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.structure import Structure, is_xref

#: Characters the 7.0 ``banned`` production forbids anywhere in a data stream.
BANNED_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f\ud800-\udfff\ufffe\uffff]")

_LINE_RE = re.compile(r"^(\d+) (?:(@[^@ ]+@) )?([A-Za-z0-9_]+)(?: (.*))?$", re.DOTALL)
_LOOSE_LINE_RE = re.compile(r"^\s*(\d+)\s+(?:(@[^@ ]+@)\s+)?([A-Za-z0-9_]+)(?: (.*))?$", re.DOTALL)
_STD_TAG_RE = re.compile(r"^(?:[A-Z][A-Z0-9_]*|_[A-Z0-9_]+)$")
_LOOSE_POINTER_RE = re.compile(r"^@[^@#\s][^@]*@$")
_TERMINATOR_RE = re.compile(r"\r\n|\r|\n")
_DATE_ESCAPE_RE = re.compile(r"@#D[^@]*@")

DEFAULT_MAX_DEPTH = 128


@dataclass(frozen=True, slots=True)
class Dialect:
    """Line-level rules that differ between GEDCOM versions."""

    name: str
    continuation_tags: frozenset[str]
    escape_all_at_signs: bool
    loose_pointers: bool


GEDCOM7 = Dialect("7.0", frozenset({"CONT"}), escape_all_at_signs=False, loose_pointers=False)
GEDCOM551 = Dialect(
    "5.5.1", frozenset({"CONT", "CONC"}), escape_all_at_signs=True, loose_pointers=True
)


@dataclass(frozen=True, slots=True)
class GedcomLine:
    """One tokenized line. ``value`` is the raw line value, still escaped."""

    number: int
    level: int
    xref: str | None
    tag: str
    value: str | None


def split_lines(text: str) -> list[str]:
    """Split on CR, LF or CR-LF. A single trailing terminator does not create an empty line."""
    parts = _TERMINATOR_RE.split(text)
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def strip_bom(text: str) -> str:
    return text[1:] if text.startswith("﻿") else text


def tokenize(text: str, diagnostics: Diagnostics, dialect: Dialect = GEDCOM7) -> list[GedcomLine]:
    """Tokenize decoded text into lines, recording grammar problems as diagnostics.

    Unparseable lines are kept as pseudo-lines with tag ``""`` so the builder can decide whether
    they continue the previous payload (a common vendor quirk) or must be dropped.
    """
    result: list[GedcomLine] = []
    for index, raw in enumerate(split_lines(strip_bom(text)), start=1):
        line = raw
        if BANNED_RE.search(line):
            diagnostics.error("banned-character", "control or banned character removed", index)
            line = BANNED_RE.sub("", line)
        if line == "":
            diagnostics.error("blank-line", "blank line ignored", index)
            continue
        token = _tokenize_line(line, index, diagnostics, dialect)
        result.append(token)
    return result


def _tokenize_line(
    line: str, number: int, diagnostics: Diagnostics, dialect: Dialect
) -> GedcomLine:
    match = _LINE_RE.match(line)
    if match is None:
        match = _LOOSE_LINE_RE.match(line)
        if match is None:
            return GedcomLine(number, -1, None, "", line)
        if dialect is GEDCOM7:
            diagnostics.error("line-spacing", "extra whitespace between line components", number)
        else:
            diagnostics.warning("line-spacing", "extra whitespace between line components", number)
    level_text, xref, tag, value = match.groups()
    if len(level_text) > 1 and level_text.startswith("0"):
        diagnostics.error("level-leading-zero", f"level {level_text!r} has a leading zero", number)
    level = int(level_text)
    if not _STD_TAG_RE.match(tag):
        diagnostics.error("tag-syntax", f"tag {tag!r} is not a valid tag; upper-cased", number)
        tag = tag.upper()
        if not _STD_TAG_RE.match(tag):
            tag = "_" + (tag.strip("_") or "UNKNOWN")
    if xref is not None and not dialect.loose_pointers and not is_xref(xref):
        diagnostics.error("xref-syntax", f"cross-reference {xref!r} is not a valid Xref", number)
    if xref == "@VOID@":
        diagnostics.error("xref-void", "@VOID@ cannot be used as a cross-reference id", number)
        xref = None
    if value == "":
        diagnostics.error("empty-line-value", "trailing space after tag with no line value", number)
        value = None
    return GedcomLine(number, level, xref, tag, value)


def decode_value(
    value: str | None, number: int, diagnostics: Diagnostics, dialect: Dialect
) -> tuple[str | None, str | None]:
    """Split a raw line value into ``(text, pointer)`` and undo ``@`` escaping."""
    if value is None:
        return None, None
    if dialect.loose_pointers:
        if _LOOSE_POINTER_RE.match(value):
            return None, value
        return _unescape_all(value), None
    if is_xref(value):
        return None, value
    if value.startswith("@@"):
        return value[1:], None
    if value.startswith("@"):
        diagnostics.error(
            "line-value-at", "line value starts with a single '@' and is not a pointer", number
        )
    return value, None


def _unescape_all(value: str) -> str:
    """5.5.1 doubled every ``@`` outside date escapes; undo that, leaving ``@#D...@`` alone."""
    if "@@" not in value:
        return value
    pieces: list[str] = []
    last = 0
    for match in _DATE_ESCAPE_RE.finditer(value):
        pieces.append(value[last : match.start()].replace("@@", "@"))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(value[last:].replace("@@", "@"))
    return "".join(pieces)


def build_structures(
    lines: list[GedcomLine],
    diagnostics: Diagnostics,
    dialect: Dialect = GEDCOM7,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[Structure]:
    """Assemble tokenized lines into level-0 structures (records, ``HEAD`` and ``TRLR``).

    Continuation lines are folded into their structure's payload. Level jumps, orphan lines and
    misplaced continuations are repaired and reported.
    """
    roots: list[Structure] = []
    stack: list[Structure] = []
    # The most recent structure whose payload may still receive continuation lines.
    open_payload: Structure | None = None
    for line in lines:
        if line.level < 0:
            open_payload = _handle_garbage(line, open_payload, diagnostics)
            continue
        level = line.level
        if line.tag in dialect.continuation_tags or line.tag in {"CONT", "CONC"}:
            open_payload = _continue(line, stack, open_payload, diagnostics, dialect)
            continue
        if level > max_depth:
            diagnostics.error("too-deep", f"nesting deeper than {max_depth} levels", line.number)
            level = max_depth
        if level > len(stack):
            if not stack:
                diagnostics.error(
                    "orphan-line", f"{line.tag} line has no record to belong to; dropped",
                    line.number,
                )
                open_payload = None
                continue
            diagnostics.error(
                "level-jump", f"level {line.level} follows level {len(stack) - 1}", line.number
            )
            level = len(stack)
        text, pointer = decode_value(line.value, line.number, diagnostics, dialect)
        node = Structure(tag=line.tag, payload=text, pointer=pointer, line=line.number)
        if line.xref is not None:
            if level == 0:
                node.xref = line.xref
            else:
                diagnostics.error(
                    "xref-on-substructure", "only records may carry a cross-reference id",
                    line.number,
                )
        del stack[level:]
        if level == 0:
            roots.append(node)
        else:
            stack[level - 1].children.append(node)
        stack.append(node)
        open_payload = node
    return roots


def _handle_garbage(
    line: GedcomLine, open_payload: Structure | None, diagnostics: Diagnostics
) -> Structure | None:
    text = line.value or ""
    if open_payload is not None and open_payload.pointer is None:
        diagnostics.error(
            "unparseable-line",
            "line does not match the GEDCOM line grammar; kept as a continuation of the "
            "previous payload",
            line.number,
        )
        previous = open_payload.payload or ""
        open_payload.payload = f"{previous}\n{text}"
        return open_payload
    diagnostics.error(
        "unparseable-line", f"line does not match the GEDCOM line grammar; dropped: {text[:60]!r}",
        line.number,
    )
    return open_payload


def _continue(
    line: GedcomLine,
    stack: list[Structure],
    open_payload: Structure | None,
    diagnostics: Diagnostics,
    dialect: Dialect,
) -> Structure | None:
    if line.tag not in dialect.continuation_tags:
        diagnostics.error(
            "conc-in-7", f"{line.tag} is not part of GEDCOM {dialect.name}; joined anyway",
            line.number,
        )
    if line.xref is not None:
        diagnostics.error("xref-on-substructure", "continuation lines take no xref", line.number)
    target = stack[line.level - 1] if 0 < line.level <= len(stack) else None
    if target is None:
        diagnostics.error(
            "continuation-orphan", f"{line.tag} has no structure to continue; dropped", line.number
        )
        return open_payload
    if target is not open_payload:
        diagnostics.error(
            "continuation-misplaced",
            f"{line.tag} must directly follow the line it continues; joined anyway",
            line.number,
        )
    text, pointer = decode_value(line.value, line.number, diagnostics, dialect)
    piece = text if text is not None else (pointer or "")
    if target.pointer is not None:
        diagnostics.error(
            "continuation-of-pointer",
            f"{line.tag} cannot continue a pointer; text kept as a NOTE substructure",
            line.number,
        )
        target.children.append(Structure(tag="NOTE", payload=piece or None, line=line.number))
        return target
    previous = target.payload or ""
    target.payload = f"{previous}\n{piece}" if line.tag == "CONT" else previous + piece
    return target
