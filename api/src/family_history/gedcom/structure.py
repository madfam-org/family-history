"""The generic GEDCOM structure node.

Every line-level construct ends up as a `Structure`: a tag, an optional payload (either text or a
pointer, never both), substructures in order, and a cross-reference identifier for records. The
typed model in `family_history.gedcom.model` is a view over these nodes; anything it does not
model stays here verbatim, which is what makes round trips lossless.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

VOID = "@VOID@"


@dataclass(slots=True)
class Structure:
    """One GEDCOM structure.

    ``payload`` is the decoded text (``@@`` escapes removed, continuation lines joined with
    ``"\\n"``). ``pointer`` is a cross-reference such as ``"@I1@"`` or ``"@VOID@"``. ``line`` is
    the 1-based source line and does not take part in equality.
    """

    tag: str
    payload: str | None = None
    pointer: str | None = None
    children: list[Structure] = field(default_factory=list)
    xref: str | None = None
    line: int | None = field(default=None, compare=False, repr=False)

    @property
    def is_extension(self) -> bool:
        """True for tags matching the ``extTag`` production (leading underscore)."""
        return self.tag.startswith("_")

    def first(self, tag: str) -> Structure | None:
        """The first substructure with ``tag``, or ``None``."""
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def all(self, tag: str) -> list[Structure]:
        """Every substructure with ``tag``, in order."""
        return [child for child in self.children if child.tag == tag]

    def text(self, tag: str) -> str | None:
        """The payload of the first substructure with ``tag``."""
        child = self.first(tag)
        return child.payload if child is not None else None

    def add(self, tag: str, payload: str | None = None, *, pointer: str | None = None) -> Structure:
        """Append a new substructure and return it."""
        child = Structure(tag=tag, payload=payload, pointer=pointer)
        self.children.append(child)
        return child

    def walk(self) -> Iterator[Structure]:
        """This structure and every descendant, depth first, without recursion."""
        stack: list[Structure] = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def copy(self) -> Structure:
        """A deep copy (line numbers included)."""
        clone = Structure(
            tag=self.tag, payload=self.payload, pointer=self.pointer, xref=self.xref, line=self.line
        )
        clone.children = [child.copy() for child in self.children]
        return clone


def is_xref(value: str) -> bool:
    """True when ``value`` matches the 7.0 ``Xref`` production (``@`` + tagchars + ``@``)."""
    if len(value) < 3 or value[0] != "@" or value[-1] != "@":
        return False
    return all(ch.isascii() and (ch.isupper() or ch.isdigit() or ch == "_") for ch in value[1:-1])
