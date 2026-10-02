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
    0xA1: "Ł", 0xA2: "Ø", 0xA3: "Đ", 0xA4: "Þ", 0xA5: "Æ",
    0xA6: "Œ", 0xA7: "ʹ", 0xA8: "·", 0xA9: "♭", 0xAA: "®",
    0xAB: "±", 0xAC: "Ơ", 0xAD: "Ư", 0xAE: "ʼ", 0xB0: "ʻ",
    0xB1: "ł", 0xB2: "ø", 0xB3: "đ", 0xB4: "þ", 0xB5: "æ",
    0xB6: "œ", 0xB7: "ʺ", 0xB8: "ı", 0xB9: "£", 0xBA: "ð",
    0xBC: "ơ", 0xBD: "ư", 0xBE: "□", 0xBF: "■", 0xC0: "°",
    0xC1: "ℓ", 0xC2: "℗", 0xC3: "©", 0xC4: "♯", 0xC5: "¿",
    0xC6: "¡", 0xC7: "ß", 0xC8: "€",
}

#: Combining diacritics; in ANSEL they precede the base character.
COMBINING: dict[int, str] = {
    0xE0: "̉", 0xE1: "̀", 0xE2: "́", 0xE3: "̂", 0xE4: "̃",
    0xE5: "̄", 0xE6: "̆", 0xE7: "̇", 0xE8: "̈", 0xE9: "̌",
    0xEA: "̊", 0xEB: "︠", 0xEC: "︡", 0xED: "̕", 0xEE: "̋",
    0xEF: "̐", 0xF0: "̧", 0xF1: "̨", 0xF2: "̣", 0xF3: "̤",
    0xF4: "̥", 0xF5: "̳", 0xF6: "̲", 0xF7: "̦", 0xF8: "̜",
    0xF9: "̮", 0xFA: "︢", 0xFB: "︣", 0xFE: "̓",
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
