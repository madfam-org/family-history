"""Shared helpers for the GEDCOM engine tests. All fixtures are synthetic (invented people)."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "gedcom"
SEVEN_FIXTURE = "familia-sintetica-7.ged"
MINIMAL_HEAD = "0 HEAD\n1 GEDC\n2 VERS 7.0\n"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def dataset(body: str) -> str:
    """Wrap record lines in a minimal valid 7.0 header and trailer."""
    if body and not body.endswith("\n"):
        body += "\n"
    return MINIMAL_HEAD + body + "0 TRLR\n"
