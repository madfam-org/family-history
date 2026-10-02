"""Diagnostics shared by every GEDCOM reader and writer.

A reader never stops at the first problem. It records a `Diagnostic` for each one, with the
line number it came from, and keeps going. Strict mode then raises `GedcomStrictError` carrying
every error-level diagnostic; tolerant mode hands the diagnostics back as an import report.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """How bad a diagnostic is.

    ``ERROR`` is a violation of the specification. ``WARNING`` means the input was repaired or
    converted and something may have changed. ``INFO`` records a decision worth knowing about.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One finding about the input, with the 1-based line it came from when known."""

    severity: Severity
    code: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line is not None else ""
        return f"{where}{self.severity.value} [{self.code}] {self.message}"


class GedcomError(Exception):
    """Base class for every error raised by `family_history.gedcom`."""


class GedcomSyntaxError(GedcomError):
    """Input that cannot be read at all (for example, undecodable bytes in strict mode)."""

    def __init__(self, message: str, line: int | None = None) -> None:
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{message}")


class GedcomStrictError(GedcomError):
    """Raised by strict-mode readers when the input violates the specification.

    ``diagnostics`` holds every finding, not only the first, so a caller can show them all.
    """

    def __init__(self, diagnostics: Iterable[Diagnostic]) -> None:
        self.diagnostics: tuple[Diagnostic, ...] = tuple(diagnostics)
        errors = [d for d in self.diagnostics if d.severity is Severity.ERROR]
        head = "; ".join(str(d) for d in errors[:5])
        more = f" (and {len(errors) - 5} more)" if len(errors) > 5 else ""
        super().__init__(f"{len(errors)} specification violation(s): {head}{more}")


@dataclass(slots=True)
class Diagnostics:
    """An append-only collector of diagnostics."""

    strict: bool = True
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, line: int | None = None) -> None:
        """Record a specification violation.

        Strict collectors keep it as an error; tolerant collectors record it as a warning,
        because the reader repaired or set aside the offending input and carried on.
        """
        severity = Severity.ERROR if self.strict else Severity.WARNING
        self.items.append(Diagnostic(severity, code, message, line))

    def warning(self, code: str, message: str, line: int | None = None) -> None:
        self.items.append(Diagnostic(Severity.WARNING, code, message, line))

    def info(self, code: str, message: str, line: int | None = None) -> None:
        self.items.append(Diagnostic(Severity.INFO, code, message, line))

    def extend(self, other: Iterable[Diagnostic]) -> None:
        self.items.extend(other)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self.items)

    def raise_if_errors(self) -> None:
        """Raise `GedcomStrictError` when any error-level diagnostic was recorded."""
        if self.has_errors:
            raise GedcomStrictError(self.items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)
