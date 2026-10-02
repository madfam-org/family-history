"""Shared helpers for the GEDCOM engine tests. All fixtures are synthetic (invented people)."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "gedcom"
SEVEN_FIXTURE = "familia-sintetica-7.ged"
MINIMAL_HEAD = "0 HEAD\n1 GEDC\n2 VERS 7.0\n"
UTF8_BOM = b"\xef\xbb\xbf"
# Fixtures that stand for files exported WITH a UTF-8 byte-order mark. The mark is added at run
# time, not stored on disk, so the repository's byte gate (no BOM in tracked text) holds while the
# importer's BOM handling is still exercised with exactly the bytes a vendor writes.
BOM_FIXTURES = frozenset({"rootsmagic-like-551.ged"})


def fixture_bytes(name: str) -> bytes:
    data = (FIXTURES / name).read_bytes()
    return UTF8_BOM + data if name in BOM_FIXTURES else data


def dataset(body: str) -> str:
    """Wrap record lines in a minimal valid 7.0 header and trailer."""
    if body and not body.endswith("\n"):
        body += "\n"
    return MINIMAL_HEAD + body + "0 TRLR\n"
