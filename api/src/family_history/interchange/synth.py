"""`domain.synth.generate_family` → Tree, for `python -m family_history.cli seed-synth`."""

from __future__ import annotations

from datetime import date

from family_history.domain import names as domain_names
from family_history.domain.dates import format_date_value
from family_history.domain.events import AssociationRole as DomainRole
from family_history.domain.sensitivity import Sensitivity as DomainSensitivity
from family_history.domain.synth import SyntheticFamily, generate_family
from family_history.interchange.tree import (
    FIELD_CAUSE_OF_DEATH,
    FIELD_OCCURRED,
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

PLACE_KINDS = {
    "country": "pais",
    "state": "estado",
    "locality": "localidad",
    "pueblo": "localidad",
    "villa": "localidad",
    "parish": "parroquia",
}
SOURCE_PREFIXES = (("civil_", "civil_registry_act"), ("parroquial_", "parish_book"))
NAME_TYPES = {
    domain_names.NameType.BIRTH: "birth",
    domain_names.NameType.BAPTISM: "baptismal",
    domain_names.NameType.MARRIED: "married",
    domain_names.NameType.AKA: "aka",
    domain_names.NameType.RELIGIOUS: "religious",
    domain_names.NameType.IMMIGRANT: "immigrant",
}
ROLES = {DomainRole.GODPARENT: "godparent", DomainRole.WITNESS: "witness",
         DomainRole.OFFICIANT: "officiant", DomainRole.CLERGY: "officiant"}  # fmt: skip


def _source_type(kind: str) -> str:
    if kind == "oral":
        return "oral_interview"
    for prefix, value in SOURCE_PREFIXES:
        if kind.startswith(prefix):
            return value
    return "other"


def _name(form: domain_names.NameForm, primary: bool) -> TName:
    particles = {
        k: v
        for k, v in (("paterno", form.particle_paterno), ("materno", form.particle_materno))
        if v
    }
    order = (
        "paterno_materno"
        if form.surname_order is domain_names.SurnameOrder.PATERNO_FIRST
        else "materno_paterno"
    )
    return TName(
        given=form.nombre_de_pila or None,
        apellido_paterno=form.apellido_paterno,
        apellido_materno=form.apellido_materno,
        extra_surnames=list(form.extra_surnames),
        particles=particles,
        nombre_usado=form.nombre_usado,
        nicknames=list(form.apodos),
        name_type=NAME_TYPES.get(form.name_type, "other"),
        lang=form.lang,
        surname_order=order,
        is_primary=primary,
    )


def family_tree(family: SyntheticFamily) -> Tree:
    tree = Tree()
    tree.places = [
        TPlace(p.id, p.name, PLACE_KINDS.get(p.kind, "other"), p.parent_id, order=p.id)
        for p in family.places
    ]
    tree.sources = [
        TSource(s.id, _source_type(s.kind), s.title, s.repository, {}, s.id) for s in family.sources
    ]
    tree.citations = [TCitation(c.id, c.source_id, c.page, order=c.id) for c in family.citations]
    tree.people = [
        TPerson(
            p.id,
            p.sex.value,
            "space",
            [_name(n, i == 0) for i, n in enumerate(p.names)],
            order=p.id,
        )  # fmt: skip
        for p in family.people
    ]
    associations: dict[str, list[TAssociation]] = {}
    for assoc in family.associations:
        role = ROLES.get(assoc.role, "other")
        phrase = assoc.occasion.label_es if assoc.occasion is not None else None
        associations.setdefault(assoc.event_id, []).append(
            TAssociation(assoc.person_id, role, phrase if role == "other" else None)
        )
    for event in family.events:
        sensitivity = event.sensitivity
        tree.events.append(
            TEvent(
                event.id,
                event.event_type.value,
                format_date_value(event.date) or None,
                None,
                event.place_id,
                event.value,
                None if sensitivity is DomainSensitivity.NONE else sensitivity.value,
                [TParticipant(p, "principal") for p in event.principals],
                [a for a in associations.get(event.id, []) if a.person not in event.principals],
                order=event.id,
            )
        )
        if event.citation_ids:
            tree.assertions.append(
                TAssertion(
                    f"A-{event.id}",
                    "event",
                    event.id,
                    FIELD_OCCURRED,
                    True,
                    "accepted",
                    None,
                    list(event.citation_ids),
                    order=f"A-{event.id}",
                )  # fmt: skip
            )
        if event.cause:
            tree.assertions.append(
                TAssertion(
                    f"K-{event.id}",
                    "event",
                    event.id,
                    FIELD_CAUSE_OF_DEATH,
                    event.cause,
                    "suggested",
                    "health",
                    [],
                    order=f"K-{event.id}",
                )  # fmt: skip
            )
    tree.unions = [
        TUnion(f"U{i}", (link.a, link.b), link.status.value, order=f"U{i:06d}")
        for i, link in enumerate(family.partner_links)
    ]
    tree.parent_links = [
        TParentLink(f"R{i}", link.parent, link.child, link.pedigree.value, order=f"R{i:06d}")
        for i, link in enumerate(family.parent_links)
    ]
    return tree


def synthetic_tree(seed: int, generations: int, today: date | None = None) -> Tree:
    family = (
        generate_family(seed, generations)
        if today is None
        else generate_family(seed, generations, today=today)
    )
    return family_tree(family)
