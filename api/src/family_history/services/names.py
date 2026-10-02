"""Names through `family_history.domain.names`, and the search columns the API maintains.

The API keeps its own name-form row (the v1 contract) and converts it to a domain `NameForm` to
render it: `display_name` is the FORMAL style («María Guadalupe de la Garza Treviño») and
`sort_name` the SORTING style («Garza Treviño, María Guadalupe de la»).

Two columns are maintained on every names write:

- `person.sort_name`: the collation key of the SORTING display (lowercase, accents stripped), the
  keyset-pagination order of people lists;
- `person.search_tokens`: every name part folded by `normalize_for_search`, space-padded
  (` tok1 tok2 `) so a `LIKE` can tell an exact token from a prefix (services/search.py).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

from family_history.domain import names as domain_names
from family_history.domain.names import DisplayStyle, normalize_for_search
from family_history.models import NameForm
from family_history.models.enums import NameType, SurnameOrder

_NON_WORD = re.compile(r"[^\w']+", re.UNICODE)
_SPACES = re.compile(r"\s+")

_NAME_TYPES: dict[str, domain_names.NameType] = {
    NameType.BIRTH.value: domain_names.NameType.BIRTH,
    NameType.BAPTISMAL.value: domain_names.NameType.BAPTISM,
    NameType.MARRIED.value: domain_names.NameType.MARRIED,
    NameType.RELIGIOUS.value: domain_names.NameType.RELIGIOUS,
    NameType.ALSO_KNOWN_AS.value: domain_names.NameType.AKA,
    NameType.IMMIGRANT.value: domain_names.NameType.IMMIGRANT,
    NameType.OTHER.value: domain_names.NameType.AKA,
}
_ORDERS: dict[str, domain_names.SurnameOrder] = {
    SurnameOrder.PATERNO_MATERNO.value: domain_names.SurnameOrder.PATERNO_FIRST,
    SurnameOrder.MATERNO_PATERNO.value: domain_names.SurnameOrder.MATERNO_FIRST,
    SurnameOrder.SINGLE.value: domain_names.SurnameOrder.PATERNO_FIRST,
}


def normalize(text: str) -> str:
    """Lowercase, strip accents (á→a, ñ→n, ü→u) and collapse punctuation and whitespace.

    A collation key, not a search key: it keeps spelling (z stays z), so lists sort as people
    expect. Search uses `normalize_for_search`, which also folds spellings that sound alike.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = _NON_WORD.sub(" ", stripped.casefold())
    return _SPACES.sub(" ", cleaned).strip()


def query_tokens(query: str, limit: int = 8) -> list[str]:
    """Plain query tokens (places and sources search)."""
    return [token for token in normalize(query).split(" ") if token][:limit]


def like_pattern(token: str) -> str:
    """A `LIKE` pattern that matches `token` anywhere, with wildcards escaped."""
    return f"%{escape_like(token)}%"


def escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def primary_name(names: Sequence[NameForm]) -> NameForm | None:
    for name in names:
        if name.is_primary:
            return name
    return names[0] if names else None


def _clean(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _particle_and_surname(name: NameForm, which: str) -> tuple[str | None, str | None]:
    """A known particle stays apart; any other text is kept in front of the surname."""
    surname = _clean(name.apellido_paterno if which == "paterno" else name.apellido_materno)
    raw = (name.particles or {}).get(which)
    particle = _clean(raw if isinstance(raw, str) else None)
    if surname is None or particle is None:
        return None, surname
    if particle.lower() in domain_names.PARTICLES:
        return particle, surname
    return None, f"{particle} {surname}"


def to_domain(name: NameForm) -> domain_names.NameForm:
    """The domain view of an API name form. Never raises for a form the API accepted."""
    given = _clean(name.given) or _clean(name.nombre_de_pila)
    particle_paterno, paterno = _particle_and_surname(name, "paterno")
    particle_materno, materno = _particle_and_surname(name, "materno")
    extra = tuple(s for s in (_clean(x) for x in (name.extra_surnames or [])) if s)
    apodos = tuple(a for a in (_clean(x) for x in (name.nicknames or [])) if a)
    usado = _clean(name.nombre_usado)
    given_names: tuple[str, ...] = (given,) if given else ()
    if not (given_names or paterno or materno or extra or apodos) and usado:
        given_names = (usado,)
    lang = name.lang if name.lang else "es-MX"
    try:
        return domain_names.NameForm(
            given_names=given_names,
            apellido_paterno=paterno,
            apellido_materno=materno,
            particle_paterno=particle_paterno,
            particle_materno=particle_materno,
            extra_surnames=extra,
            nombre_usado=usado,
            apodos=apodos,
            name_type=_NAME_TYPES.get(name.name_type, domain_names.NameType.BIRTH),
            lang=lang,
            surname_order=_ORDERS.get(name.surname_order, domain_names.SurnameOrder.PATERNO_FIRST),
        )
    except ValueError:
        # A language tag the domain's BCP 47 check refuses: render with the default.
        return domain_names.NameForm(
            given_names=given_names,
            apellido_paterno=paterno,
            apellido_materno=materno,
            particle_paterno=particle_paterno,
            particle_materno=particle_materno,
            extra_surnames=extra,
            nombre_usado=usado,
            apodos=apodos,
            surname_order=_ORDERS.get(name.surname_order, domain_names.SurnameOrder.PATERNO_FIRST),
        )


def display_name(name: NameForm | None) -> str:
    if name is None:
        return ""
    return domain_names.display_name(to_domain(name), DisplayStyle.FORMAL)


def sorting_display(name: NameForm | None) -> str:
    """«Garza Treviño, María Guadalupe de la»: what the API returns as `sort_name`."""
    if name is None:
        return ""
    return domain_names.display_name(to_domain(name), DisplayStyle.SORTING)


def sort_key(name: NameForm | None) -> str:
    """The collation key stored in `person.sort_name`."""
    return normalize(sorting_display(name))


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


def search_tokens(names: Iterable[NameForm]) -> str:
    """` tok1 tok2 ` for `person.search_tokens`: every part of every form, folded once."""
    seen: dict[str, None] = {}
    for name in names:
        for part in _parts(name):
            for token in normalize_for_search(part).split(" "):
                if token:
                    seen.setdefault(token, None)
    return f" {' '.join(seen)} " if seen else ""
