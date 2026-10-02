"""Canonical ordering for exports: export-local ids from a stable sort of exported content.

Each entity gets an id from the sort of what is exported about it (never a database id, a
requester or a time), with the loader's `order` as the last tie-break. Importing an export
creates rows whose ids keep the file order (persist.OrderedIds), so exact ties re-export in the
same order and an export, import, export cycle is byte-identical.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from family_history.domain.names import DisplayStyle, display_name
from family_history.interchange.tree import (
    TAssertion,
    TAssociation,
    TCitation,
    TEvent,
    TName,
    TParentLink,
    TParticipant,
    TPerson,
    TPlace,
    Tree,
    TSource,
    TUnion,
)
from family_history.models import NameForm
from family_history.services.dates import bounds, stored_value
from family_history.services.names import normalize, to_domain

# -- canonical ordering ----------------------------------------------------------------------


def _number(ref: str) -> int:
    return int(ref[1:])


def _assign[T](
    items: Sequence[T], prefix: str, key: Callable[[T], Any], order: Callable[[T], str]
) -> dict[int, str]:
    ranked = sorted(range(len(items)), key=lambda i: (key(items[i]), order(items[i])))
    return {index: f"{prefix}{position + 1}" for position, index in enumerate(ranked)}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def name_record(name: TName) -> dict[str, Any]:
    return {
        "given": name.given,
        "apellido_paterno": name.apellido_paterno,
        "apellido_materno": name.apellido_materno,
        "extra_surnames": list(name.extra_surnames),
        "particles": dict(sorted(name.particles.items())),
        "nombre_de_pila": name.nombre_de_pila,
        "nombre_usado": name.nombre_usado,
        "nicknames": list(name.nicknames),
        "name_type": name.name_type,
        "lang": name.lang,
        "surname_order": name.surname_order,
        "is_primary": name.is_primary,
    }


def person_sort_key(person: TPerson) -> str:
    """The collation key of the primary name's SORTING display."""
    primary = next(
        (n for n in person.names if n.is_primary), person.names[0] if person.names else None
    )
    if primary is None:
        return ""
    form = NameForm(**{k: v for k, v in name_record(primary).items()})
    return normalize(display_name(to_domain(form), DisplayStyle.SORTING))


def date_key(date_value: str | None) -> str:
    value = stored_value(date_value)
    earliest = bounds(value)[0] if value is not None else None
    return earliest.isoformat() if earliest else "~"


def _remap(refs: dict[str, str], ref: str | None) -> str | None:
    return refs[ref] if ref is not None else None


def canonicalize(tree: Tree) -> Tree:
    """A copy of `tree` with export-local ids assigned by content, every list in id order."""
    refs: dict[str, str] = {}

    def path(place: TPlace, by_ref: dict[str, TPlace]) -> tuple[Any, ...]:
        chain: list[tuple[str, ...]] = []
        current: TPlace | None = place
        while current is not None and len(chain) < 64:
            chain.append((current.name, current.kind, str(current.valid_from or ""),
                          str(current.valid_to or ""), current.inegi_code or ""))  # fmt: skip
            current = by_ref.get(current.parent) if current.parent else None
        return tuple(reversed(chain))

    places_by_ref = {p.ref: p for p in tree.places}
    for index, ref in _assign(tree.places, "L", lambda p: path(p, places_by_ref), _order).items():
        refs[tree.places[index].ref] = ref
    for index, ref in _assign(
        tree.sources,
        "S",
        lambda s: (s.title, s.type, s.repository or "", sorted(s.locator.items())),
        _order,
    ).items():
        refs[tree.sources[index].ref] = ref
    for index, ref in _assign(
        tree.citations,
        "C",
        lambda c: (
            _number(refs[c.source]),
            c.page or "",
            c.foja or "",
            c.partida or "",
            -1 if c.quality is None else c.quality,
            c.extracted_text or "",
        ),  # fmt: skip
        _order,
    ).items():
        refs[tree.citations[index].ref] = ref
    for index, ref in _assign(
        tree.people,
        "P",
        lambda p: (
            person_sort_key(p),
            _json([name_record(n) for n in p.names]),
            p.sex,
            p.visibility,
        ),  # fmt: skip
        _order,
    ).items():
        refs[tree.people[index].ref] = ref

    events = [_event_local(e, refs) for e in tree.events]
    for index, ref in _assign(
        events, "E", lambda e: (date_key(e.date_value), _json(event_record(e))), _order
    ).items():
        refs[tree.events[index].ref] = ref
        events[index].ref = ref
    unions = [
        TUnion(u.ref, _pair(refs[u.partners[0]], refs[u.partners[1]]), u.status, u.order)
        for u in tree.unions
    ]
    for index, ref in _assign(
        unions, "F", lambda u: (_number(u.partners[0]), _number(u.partners[1]), u.status), _order
    ).items():
        refs[unions[index].ref] = ref
        unions[index].ref = ref
    links = [
        TParentLink(x.ref, refs[x.parent], refs[x.child], x.pedigree, x.order)
        for x in tree.parent_links
    ]
    for index, ref in _assign(
        links, "R", lambda x: (_number(x.parent), _number(x.child), x.pedigree), _order
    ).items():
        refs[links[index].ref] = ref
        links[index].ref = ref
    assertions = [
        TAssertion(
            a.ref,
            a.subject_type,
            refs[a.subject],
            a.field,
            a.value,
            a.status,
            a.sensitivity,
            sorted((refs[c] for c in a.citations), key=_number),
            a.order,
        )  # fmt: skip
        for a in tree.assertions
    ]
    for index, ref in _assign(
        assertions,
        "A",
        lambda a: (
            a.subject_type,
            a.subject[0],
            _number(a.subject),
            a.field,
            _json(a.value),
            a.status,
            a.sensitivity or "",
            [_number(c) for c in a.citations],
        ),  # fmt: skip
        _order,
    ).items():
        assertions[index].ref = ref

    out = Tree()
    out.places = _sorted(
        TPlace(
            refs[p.ref],
            p.name,
            p.kind,
            _remap(refs, p.parent),
            p.valid_from,
            p.valid_to,
            p.inegi_code,
            p.order,
        )  # fmt: skip
        for p in tree.places
    )
    out.sources = _sorted(
        TSource(
            refs[s.ref], s.type, s.title, s.repository, dict(sorted(s.locator.items())), s.order
        )
        for s in tree.sources
    )
    out.citations = _sorted(
        TCitation(
            refs[c.ref],
            refs[c.source],
            c.page,
            c.foja,
            c.partida,
            c.quality,
            c.extracted_text,
            c.order,
        )  # fmt: skip
        for c in tree.citations
    )
    out.people = _sorted(
        TPerson(refs[p.ref], p.sex, p.visibility, list(p.names), p.living_status, p.order)
        for p in tree.people
    )
    out.events = _sorted(events)
    out.unions = _sorted(unions)
    out.parent_links = _sorted(links)
    out.assertions = _sorted(assertions)
    return out


def _order(item: Any) -> str:
    return str(item.order)


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if _number(a) <= _number(b) else (b, a)


def _sorted[T](items: Iterable[T]) -> list[T]:
    return sorted(items, key=lambda item: _number(item.ref))  # type: ignore[attr-defined]


def _event_local(event: TEvent, refs: dict[str, str]) -> TEvent:
    participants = sorted(
        (TParticipant(refs[p.person], p.role) for p in event.participants),
        key=lambda p: (_number(p.person), p.role),
    )
    associations = sorted(
        (TAssociation(refs[a.person], a.role, a.phrase) for a in event.associations),
        key=lambda a: (_number(a.person), a.role, a.phrase or ""),
    )
    return TEvent(
        event.ref, event.type, event.date_value, event.date_original, _remap(refs, event.place),
        event.description, event.sensitivity, participants, associations, event.order,
    )  # fmt: skip


def event_record(event: TEvent) -> dict[str, Any]:
    return {
        "type": event.type,
        "date_value": event.date_value,
        "date_original": event.date_original,
        "place": event.place,
        "description": event.description,
        "sensitivity": event.sensitivity,
        "participants": [{"person": p.person, "role": p.role} for p in event.participants],
        "associations": [
            {"person": a.person, "role": a.role, "phrase": a.phrase} for a in event.associations
        ],
    }
