"""Serialize `Structure` trees to GEDCOM lines, for 7.0 or 5.5.1.

* Multi-line payloads become ``CONT`` lines (both versions).
* 7.0 doubles only a leading ``@``; 5.5.1 doubles every ``@`` except in ``@#D...@`` date
  escapes.
* 5.5.1 lines are limited to 255 characters; longer payload lines are split with ``CONC`` at a
  point that leaves no leading or trailing space on either side, since many legacy readers
  trim those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from family_history.gedcom.structure import Structure

_DATE_ESCAPE_RE = re.compile(r"@#D[^@]*@")
_TERMINATORS_RE = re.compile(r"\r\n|\r")


@dataclass(frozen=True, slots=True)
class EmitOptions:
    escape_all_at_signs: bool = False
    max_line_length: int | None = None


GEDCOM7_EMIT = EmitOptions()
GEDCOM551_EMIT = EmitOptions(escape_all_at_signs=True, max_line_length=255)


def _escape(text: str, options: EmitOptions) -> str:
    if options.escape_all_at_signs:
        pieces: list[str] = []
        last = 0
        for match in _DATE_ESCAPE_RE.finditer(text):
            pieces.append(text[last : match.start()].replace("@", "@@"))
            pieces.append(match.group(0))
            last = match.end()
        pieces.append(text[last:].replace("@", "@@"))
        return "".join(pieces)
    return "@" + text if text.startswith("@") else text


def _escaped_length(text: str, options: EmitOptions) -> int:
    return len(_escape(text, options))


def _split_for_conc(text: str, first_budget: int, budget: int, options: EmitOptions) -> list[str]:
    """Split ``text`` into chunks whose escaped length fits the budgets."""
    chunks: list[str] = []
    rest = text
    limit = first_budget
    while _escaped_length(rest, options) > limit:
        cut = _cut_point(rest, limit, options)
        chunks.append(rest[:cut])
        rest = rest[cut:]
        limit = budget
    chunks.append(rest)
    return chunks


def _cut_point(text: str, limit: int, options: EmitOptions) -> int:
    # Largest prefix length whose escaped form fits.
    size = 0
    fit = 0
    for index, char in enumerate(text):
        size += 2 if (char == "@" and options.escape_all_at_signs) else 1
        if size > limit:
            break
        fit = index + 1
    fit = max(fit, 1)
    # Prefer a cut with no space on either side of it.
    for cut in range(fit, max(fit // 2, 1) - 1, -1):
        if 0 < cut < len(text) and text[cut - 1] != " " and text[cut] != " ":
            if not _inside_date_escape(text, cut):
                return cut
    return fit


def _inside_date_escape(text: str, cut: int) -> bool:
    return any(m.start() < cut < m.end() for m in _DATE_ESCAPE_RE.finditer(text))


def emit_lines(roots: list[Structure], options: EmitOptions = GEDCOM7_EMIT) -> list[str]:
    """Render level-0 structures as lines without terminators."""
    out: list[str] = []
    stack: list[tuple[int, Structure]] = [(0, root) for root in reversed(roots)]
    while stack:
        level, node = stack.pop()
        _emit_one(level, node, out, options)
        stack.extend((level + 1, child) for child in reversed(node.children))
    return out


def _emit_one(level: int, node: Structure, out: list[str], options: EmitOptions) -> None:
    head = f"{level} {node.xref} {node.tag}" if node.xref and level == 0 else f"{level} {node.tag}"
    if node.pointer is not None:
        out.append(f"{head} {node.pointer}")
        return
    if not node.payload:
        out.append(head)
        return
    parts = _TERMINATORS_RE.sub("\n", node.payload).split("\n")
    _emit_text(head, parts[0], level, out, options)
    for part in parts[1:]:
        _emit_text(f"{level + 1} CONT", part, level, out, options)


def _emit_text(head: str, text: str, level: int, out: list[str], options: EmitOptions) -> None:
    if text == "":
        out.append(head)
        return
    if options.max_line_length is None:
        out.append(f"{head} {_escape(text, options)}")
        return
    conc_head = f"{level + 1} CONC"
    first_budget = max(options.max_line_length - len(head) - 1, 1)
    budget = max(options.max_line_length - len(conc_head) - 1, 1)
    chunks = _split_for_conc(text, first_budget, budget, options)
    out.append(f"{head} {_escape(chunks[0], options)}")
    out.extend(f"{conc_head} {_escape(chunk, options)}" for chunk in chunks[1:])


def render(lines: list[str], line_ending: str = "\n") -> str:
    return line_ending.join(lines) + line_ending
