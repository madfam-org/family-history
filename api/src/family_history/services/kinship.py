"""Kinship and compadrazgo through `family_history.domain.kinship` and `domain.compadrazgo`.

The family graph is built from what the caller can see in one space: people who are not
soft-deleted and not someone else's private person, and relationships whose both ends are
visible. Godparent links come from `association` rows with role `godparent` on sacraments and
celebrations the caller may see; the godchild is the event's principal (both spouses for a
wedding). Nothing derived here is stored.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select

from family_history.domain.compadrazgo import (
    CompadrazgoRole,
    GodparentLink,
    Occasion,
    compadrazgo,
)
from family_history.domain.events import EventType
from family_history.domain.kinship import (
    FamilyGraph,
    Kinship,
    ParentLink,
    PartnerLink,
    PartnerStatus,
    Pedigree,
    Sex,
    kinship,
)
from family_history.models import Association, Event, EventParticipant, Person, Relationship
from family_history.models.enums import AssociationRole, ParticipantRole, RelationshipType
from family_history.services.access import SpaceContext
from family_history.services.privacy import sensitive_visible, treated_as_living, visible_people

OCCASIONS: dict[str, Occasion] = {
    EventType.BAPTISM.value: Occasion.BAUTIZO,
    EventType.CHRISTENING.value: Occasion.BAUTIZO,
    EventType.CONFIRMATION.value: Occasion.CONFIRMACION,
    EventType.FIRST_COMMUNION.value: Occasion.PRIMERA_COMUNION,
    EventType.RELIGIOUS_MARRIAGE.value: Occasion.BODA,
    EventType.MARRIAGE.value: Occasion.BODA,
    EventType.QUINCEANERA.value: Occasion.XV_ANOS,
}
GODCHILD_ROLES = (ParticipantRole.PRINCIPAL.value, ParticipantRole.SPOUSE.value)


@dataclass(frozen=True)
class SpaceGraph:
    graph: FamilyGraph
    people: dict[uuid.UUID, Person]


def build_graph(ctx: SpaceContext) -> SpaceGraph:
    people = {
        person.id: person
        for person in ctx.db.scalars(
            select(Person).where(Person.family_space_id == ctx.space_id, visible_people(ctx.sub))
        ).all()
    }
    parents: list[ParentLink] = []
    partners: list[PartnerLink] = []
    rows = ctx.db.scalars(
        select(Relationship).where(Relationship.family_space_id == ctx.space_id)
    ).all()
    for row in rows:
        if row.from_person_id not in people or row.to_person_id not in people:
            continue
        a, b = str(row.from_person_id), str(row.to_person_id)
        if row.type == RelationshipType.PARENT_CHILD.value:
            parents.append(ParentLink(a, b, Pedigree(row.pedigree or Pedigree.BIRTH.value)))
        else:
            status = PartnerStatus(row.partner_status or PartnerStatus.MARRIED.value)
            partners.append(PartnerLink(a, b, status))
    sexes = {str(person_id): Sex(person.sex) for person_id, person in people.items()}
    return SpaceGraph(FamilyGraph(sexes, parents, partners), people)


def relation(graph: SpaceGraph, ego: uuid.UUID, alter: uuid.UUID) -> Kinship | None:
    return kinship(graph.graph, str(ego), str(alter))


def godparent_links(ctx: SpaceContext, graph: SpaceGraph) -> list[GodparentLink]:
    """Godparent associations the caller may see, one link per godchild."""
    rows = ctx.db.execute(
        select(
            Association.event_id,
            Association.person_id,
            Event.type,
            Event.sensitivity,
            Event.created_by,
        )
        .join(Event, Event.id == Association.event_id)
        .where(
            Association.family_space_id == ctx.space_id,
            Association.role == AssociationRole.GODPARENT.value,
            Event.type.in_(list(OCCASIONS)),
        )
    ).all()
    if not rows:
        return []
    godchildren: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for event_id, person_id in ctx.db.execute(
        select(EventParticipant.event_id, EventParticipant.person_id).where(
            EventParticipant.event_id.in_([row.event_id for row in rows]),
            EventParticipant.role.in_(GODCHILD_ROLES),
        )
    ).tuples():
        if person_id in graph.people:
            godchildren[event_id].append(person_id)
    links: list[GodparentLink] = []
    for event_id, godparent, event_type, sensitivity, author in rows:
        children = godchildren.get(event_id, [])
        if godparent not in graph.people or not children:
            continue
        about_living = any(treated_as_living(graph.people[c].living_status) for c in children)
        if not sensitive_visible(sensitivity, author, ctx.sub, about_living):
            continue
        for child in children:
            if child != godparent:
                links.append(GodparentLink(str(godparent), str(child), OCCASIONS[event_type]))
    return links


@dataclass(frozen=True)
class CompadrazgoItem:
    person_id: uuid.UUID
    relation: CompadrazgoRole
    sacrament: Occasion
    label_es: str
    label_en: str


def compadrazgo_of(ctx: SpaceContext, ego: uuid.UUID) -> list[CompadrazgoItem]:
    graph = build_graph(ctx)
    relations = compadrazgo(graph.graph, godparent_links(ctx, graph), str(ego))
    items: dict[tuple[str, str, str], CompadrazgoItem] = {}
    for found in relations:
        key = (found.alter, found.role.value, found.occasion.value)
        items.setdefault(
            key,
            CompadrazgoItem(
                person_id=uuid.UUID(found.alter),
                relation=found.role,
                sacrament=found.occasion,
                label_es=found.label_es,
                label_en=found.label_en,
            ),
        )
    return list(items.values())
