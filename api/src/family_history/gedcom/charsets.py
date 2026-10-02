"""Byte decoding for GEDCOM 7.0 (UTF-8 only) and GEDCOM 5.5.1 (``HEAD.CHAR``-driven).

GEDCOM 7.0 is UTF-8, with an optional byte-order mark. UTF-16 with a BOM is accepted with a
diagnostic because older tools write it. GEDCOM 5.5.1 declares its character set in
``HEAD.CHAR``; vendors often declare one thing and write another, so the 5.5.1 decoder checks
the declaration against the bytes and reports every fallback it takes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from family_history.gedcom.ansel import decode_ansel, describe_replacements
from family_history.gedcom.diagnostics import Diagnostics

_CHAR_RE = re.compile(rb"^[ \t]*1[ \t]+CHAR[ \t]+([^\r\n]*?)[ \t]*$", re.MULTILINE)
_SNIFF_BYTES = 65536


@dataclass(frozen=True, slots=True)
class Decoded:
    """Decoded text and the encoding actually used to read it."""

    text: str
    encoding: str
    declared: str | None = None


def _line_of(data: bytes, offset: int) -> int:
    prefix = data[:offset]
    return prefix.count(b"\n") + (prefix.count(b"\r") - prefix.count(b"\r\n")) + 1


def _bom_encoding(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"
    return None


def _sniff_utf16(data: bytes) -> str | None:
    head = data[:200]
    if len(head) < 4 or b"\x00" not in head:
        return None
    even_nuls = head[0::2].count(0)
    odd_nuls = head[1::2].count(0)
    if odd_nuls > len(head) // 4 and even_nuls == 0:
        return "utf-16-le"
    if even_nuls > len(head) // 4 and odd_nuls == 0:
        return "utf-16-be"
    return None


def _decode_utf(data: bytes, encoding: str, diagnostics: Diagnostics) -> str:
    body = data
    if encoding == "utf-8" and body.startswith(b"\xef\xbb\xbf"):
        body = body[3:]
    elif encoding.startswith("utf-16") and body[:2] in (b"\xff\xfe", b"\xfe\xff"):
        body = body[2:]
    try:
        return body.decode(encoding)
    except UnicodeDecodeError as exc:
        diagnostics.error(
            "invalid-encoding",
            f"bytes are not valid {encoding}; undecodable bytes replaced with U+FFFD",
            _line_of(body, exc.start),
        )
        return body.decode(encoding, errors="replace")


def decode_gedcom7(data: bytes | str, diagnostics: Diagnostics) -> Decoded:
    """Decode a 7.0 data stream. Never raises; problems become diagnostics."""
    if isinstance(data, str):
        return Decoded(data, "str")
    encoding = _bom_encoding(data) or _sniff_utf16(data) or "utf-8"
    if encoding != "utf-8":
        diagnostics.error(
            "not-utf8", f"GEDCOM 7.0 must be UTF-8; read as {encoding} instead", 1
        )
    return Decoded(_decode_utf(data, encoding, diagnostics), encoding)


def declared_charset(data: bytes) -> str | None:
    """The ``HEAD.CHAR`` value of a single-byte or UTF-8 stream, if present."""
    match = _CHAR_RE.search(data[:_SNIFF_BYTES])
    if match is None:
        return None
    return match.group(1).decode("latin-1").strip().upper() or None


_SINGLE_BYTE = {
    "ANSI": "cp1252",
    "WINDOWS-1252": "cp1252",
    "CP1252": "cp1252",
    "IBMPC": "cp437",
    "IBM WINDOWS": "cp1252",
    "MACINTOSH": "mac_roman",
    "MACROMAN": "mac_roman",
    "ISO-8859-1": "latin-1",
    "ISO8859-1": "latin-1",
    "LATIN1": "latin-1",
}


def _is_clean_utf8_with_multibyte(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return any(ord(ch) > 0x7F for ch in text)


def decode_gedcom551(data: bytes | str, diagnostics: Diagnostics) -> Decoded:
    """Decode a 5.5.1 stream following ``HEAD.CHAR``, with fallbacks. Never raises."""
    if isinstance(data, str):
        return Decoded(data, "str")
    bom = _bom_encoding(data) or _sniff_utf16(data)
    if bom is not None:
        declared = None
        if bom == "utf-8":
            declared = declared_charset(data)
        if declared not in (None, "UTF-8", "UTF8", "UNICODE"):
            diagnostics.warning(
                "charset-mismatch", f"HEAD.CHAR says {declared} but the byte-order mark says "
                f"{bom}; the byte-order mark wins", 1,
            )
        return Decoded(_decode_utf(data, bom, diagnostics), bom, declared)
    declared = declared_charset(data)
    if declared in ("UTF-8", "UTF8"):
        return Decoded(_decode_utf(data, "utf-8", diagnostics), "utf-8", declared)
    if declared == "ANSEL":
        return _decode_declared_ansel(data, diagnostics)
    if declared in _SINGLE_BYTE:
        encoding = _SINGLE_BYTE[declared]
        diagnostics.warning(
            "charset-nonstandard",
            f"HEAD.CHAR {declared} is not a GEDCOM 5.5.1 value; read as {encoding}", 1,
        )
        return Decoded(data.decode(encoding, errors="replace"), encoding, declared)
    if declared == "UNICODE":
        diagnostics.warning(
            "charset-mismatch", "HEAD.CHAR says UNICODE but there is no UTF-16 byte-order mark; "
            "read as UTF-8", 1,
        )
    elif declared not in (None, "ASCII"):
        diagnostics.warning(
            "charset-unknown", f"unknown HEAD.CHAR {declared!r}; read as UTF-8", 1
        )
    elif declared is None:
        diagnostics.warning("charset-missing", "HEAD.CHAR is missing; read as UTF-8", 1)
    return _decode_utf8_or_cp1252(data, diagnostics, declared)


def _decode_declared_ansel(data: bytes, diagnostics: Diagnostics) -> Decoded:
    if _is_clean_utf8_with_multibyte(data):
        diagnostics.warning(
            "charset-mismatch",
            "HEAD.CHAR says ANSEL but the bytes are valid UTF-8 with non-ASCII text; read as "
            "UTF-8",
            1,
        )
        return Decoded(data.decode("utf-8"), "utf-8", "ANSEL")
    result = decode_ansel(data)
    summary = describe_replacements(result)
    if summary:
        diagnostics.warning("ansel-replacements", f"ANSEL decoded best-effort: {summary}", 1)
    else:
        diagnostics.info(
            "ansel-decoded", "ANSEL decoded; combining marks reordered and NFC-normalized", 1
        )
    return Decoded(result.text, "ansel", "ANSEL")


def _decode_utf8_or_cp1252(
    data: bytes, diagnostics: Diagnostics, declared: str | None
) -> Decoded:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        diagnostics.warning(
            "charset-fallback",
            "bytes are not valid UTF-8 (first bad byte here); read as Windows-1252",
            _line_of(data, exc.start),
        )
        return Decoded(data.decode("cp1252", errors="replace"), "cp1252", declared)
    if declared == "ASCII" and any(ord(ch) > 0x7F for ch in text):
        diagnostics.warning(
            "charset-mismatch", "HEAD.CHAR says ASCII but the text is UTF-8; read as UTF-8", 1
        )
    return Decoded(text, "utf-8", declared)
