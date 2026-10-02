"""Name display and the normalized search columns the API maintains.

Search is portable on purpose: rather than depending on the `unaccent` extension, the API keeps
`person.search_text` (every name part of every name form, lowercased with accents stripped) and
matches normalized query tokens against it with `LIKE`. When `pg_trgm` is available the
migration adds a trigram index on that column.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from family_history.models import NameForm
from family_history.models.enums import SurnameOrder

_NON_WORD = re.compile(r"[^\w']+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip accents (á→a, ñ→n, ü→u) and collapse punctuation and whitespace."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = _NON_WORD.sub(" ", stripped.casefold())
    return _SPACES.sub(" ", cleaned).strip()


def search_tokens(query: str, limit: int = 8) -> list[str]:
    return [token for token in normalize(query).split(" ") if token][:limit]


def _particle(name: NameForm, which: str) -> str | None:
    value = (name.particles or {}).get(which)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _surname(name: NameForm, which: str) -> str | None:
    surname = name.apellido_paterno if which == "paterno" else name.apellido_materno
    if not surname:
        return None
    particle = _particle(name, which)
    return f"{particle} {surname}" if particle else surname


def surnames_in_order(name: NameForm) -> list[str]:
    paterno = _surname(name, "paterno")
    materno = _surname(name, "materno")
    if name.surname_order == SurnameOrder.MATERNO_PATERNO.value:
        ordered = [materno, paterno]
    else:
        ordered = [paterno, materno]
    parts = [part for part in ordered if part]
    parts.extend(extra for extra in (name.extra_surnames or []) if extra)
    return parts


def display_name(name: NameForm | None) -> str:
    """`nombre usado` (or given names) followed by the surnames in the form's order."""
    if name is None:
        return ""
    given = name.nombre_usado or name.given or name.nombre_de_pila
    parts = [given] if given else []
    parts.extend(surnames_in_order(name))
    return " ".join(part.strip() for part in parts if part and part.strip())


def primary_name(names: Sequence[NameForm]) -> NameForm | None:
    for name in names:
        if name.is_primary:
            return name
    return names[0] if names else None


def _parts(name: NameForm) -> Iterable[str]:
    yield from (
        part
        for part in (
            name.given,
            name.nombre_de_pila,
            name.nombre_usado,
            name.apellido_paterno,
            name.apellido_materno,
        )
        if part
    )
    yield from (part for part in (name.extra_surnames or []) if part)
    yield from (part for part in (name.nicknames or []) if part)
    yield from (str(v) for v in (name.particles or {}).values() if isinstance(v, str) and v)


def search_text(names: Iterable[NameForm]) -> str:
    seen: dict[str, None] = {}
    for name in names:
        for part in _parts(name):
            for token in normalize(part).split(" "):
                if token:
                    seen.setdefault(token, None)
    return " ".join(seen)


def sort_name(name: NameForm | None) -> str:
    """Surnames first, then given names, normalized: the pagination order of people lists."""
    if name is None:
        return ""
    given = name.given or name.nombre_usado or name.nombre_de_pila or ""
    surnames = [name.apellido_paterno or "", name.apellido_materno or ""]
    return normalize(" ".join([*surnames, given]))


def like_pattern(token: str) -> str:
    """A `LIKE` pattern that matches `token` anywhere, with wildcards escaped."""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
