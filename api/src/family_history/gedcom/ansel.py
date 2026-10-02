"""Best-effort ANSEL (ANSI/NISO Z39.47) decoding, as used by GEDCOM 5.5.1 ``CHAR ANSEL``.

ANSEL writes combining diacritics *before* the letter they modify (``0xE2 'a'`` is "á"), while
Unicode writes them after. The decoder reorders them and normalizes the result to NFC. Bytes
with no ANSEL meaning become U+FFFD and are reported by value so the import report can name
every replacement.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

#: Spacing graphic characters, including the GEDCOM 5.5.1 additions (0xBE, 0xBF, 0xC7, 0xC8).
SPACING: dict[int, str] = {
    0xA1: "\u0141", 0xA2: "\u00d8", 0xA3: "\u0110", 0xA4: "\u00de", 0xA5: "\u00c6",
    0xA6: "\u0152", 0xA7: "\u02b9", 0xA8: "\u00b7", 0xA9: "\u266d", 0xAA: "\u00ae",
    0xAB: "\u00b1", 0xAC: "\u01a0", 0xAD: "\u01af", 0xAE: "\u02bc", 0xB0: "\u02bb",
    0xB1: "\u0142", 0xB2: "\u00f8", 0xB3: "\u0111", 0xB4: "\u00fe", 0xB5: "\u00e6",
    0xB6: "\u0153", 0xB7: "\u02ba", 0xB8: "\u0131", 0xB9: "\u00a3", 0xBA: "\u00f0",
    0xBC: "\u01a1", 0xBD: "\u01b0", 0xBE: "\u25a1", 0xBF: "\u25a0", 0xC0: "\u00b0",
    0xC1: "\u2113", 0xC2: "\u2117", 0xC3: "\u00a9", 0xC4: "\u266f", 0xC5: "\u00bf",
    0xC6: "\u00a1", 0xC7: "\u00df", 0xC8: "\u20ac",
}

#: Combining diacritics; in ANSEL they precede the base character.
COMBINING: dict[int, str] = {
    0xE0: "\u0309", 0xE1: "\u0300", 0xE2: "\u0301", 0xE3: "\u0302", 0xE4: "\u0303",
    0xE5: "\u0304", 0xE6: "\u0306", 0xE7: "\u0307", 0xE8: "\u0308", 0xE9: "\u030c",
    0xEA: "\u030a", 0xEB: "\ufe20", 0xEC: "\ufe21", 0xED: "\u0315", 0xEE: "\u030b",
    0xEF: "\u0310", 0xF0: "\u0327", 0xF1: "\u0328", 0xF2: "\u0323", 0xF3: "\u0324",
    0xF4: "\u0325", 0xF5: "\u0333", 0xF6: "\u0332", 0xF7: "\u0326", 0xF8: "\u031c",
    0xF9: "\u032e", 0xFA: "\ufe22", 0xFB: "\ufe23", 0xFE: "\u0313",
}


@dataclass(slots=True)
class AnselResult:
    """Decoded text plus what had to be replaced."""

    text: str
    #: Undefined byte value -> how many times it was replaced by U+FFFD.
    undefined: Counter[int] = field(default_factory=Counter)
    #: Combining marks that had no base character to attach to (kept as standalone marks).
    dangling_marks: int = 0


def decode_ansel(data: bytes) -> AnselResult:
    """Decode ANSEL bytes to NFC-normalized text. Never raises."""
    out: list[str] = []
    pending: list[str] = []
    undefined: Counter[int] = Counter()
    dangling = 0
    for byte in data:
        if byte in COMBINING:
            pending.append(COMBINING[byte])
            continue
        if byte < 0x80:
            char = chr(byte)
        elif byte in SPACING:
            char = SPACING[byte]
        else:
            undefined[byte] += 1
            char = "�"
        if pending and char in "\r\n":
            dangling += len(pending)
            out.extend(pending)
            pending.clear()
        out.append(char)
        if pending:
            out.extend(pending)
            pending.clear()
    if pending:
        dangling += len(pending)
        out.extend(pending)
    return AnselResult(unicodedata.normalize("NFC", "".join(out)), undefined, dangling)


def describe_replacements(result: AnselResult) -> str:
    """A human-readable summary naming every replacement, for the import report."""
    parts: list[str] = []
    if result.undefined:
        listed = ", ".join(
            f"0x{byte:02X} x{count}" for byte, count in sorted(result.undefined.items())
        )
        parts.append(f"undefined ANSEL bytes replaced with U+FFFD: {listed}")
    if result.dangling_marks:
        parts.append(f"{result.dangling_marks} combining mark(s) had no base letter")
    return "; ".join(parts)
