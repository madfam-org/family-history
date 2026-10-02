"""Kinship between two people and the compadrazgo of one, derived on read."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, not_found
from family_history.routers.schemas.kinship import (
    CompadrazgoItem,
    CompadrazgoList,
    KinshipOut,
    KinshipStructure,
)
from family_history.services import kinship as kinship_service
from family_history.services import people as people_service
from family_history.services.access import DbSession

router = APIRouter(prefix="/v1", tags=["kinship"], responses=ERROR_RESPONSES)


@router.get("/people/{person_id}/kinship", response_model=KinshipOut)
def get_kinship(
    person_id: uuid.UUID,
    to: Annotated[uuid.UUID, Query(description="The other person, in the same family space.")],
    principal: EarlyAccessPrincipal,
    db: DbSession,
) -> KinshipOut:
    """What `to` is to this person, with Spanish and English labels. `404 person_not_found`
    when `to` is not a person the caller can see in the same space; `404 no_relation` when the
    two are not related within eight generations."""
    ctx = people_service.resolve_person(db, principal, person_id)
    graph = kinship_service.build_graph(ctx)
    if person_id not in graph.people or to not in graph.people:
        raise not_found("person_not_found", "Person not found.")
    found = kinship_service.relation(graph, person_id, to)
    if found is None:
        raise not_found("no_relation", "The two people are not related in this family space.")
    return KinshipOut(
        kinship=KinshipStructure(
            kind=found.kind,
            up=found.up,
            down=found.down,
            half=found.half,
            adoptive=found.adoptive,
            partner_status=found.partner_status,
            via=uuid.UUID(found.via) if found.via else None,
        ),
        label_es=found.label_es,
        label_en=found.label_en,
    )


@router.get("/people/{person_id}/compadrazgo", response_model=CompadrazgoList)
def get_compadrazgo(
    person_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> CompadrazgoList:
    """Padrinos, ahijados and compadres of this person, derived from godparent associations
    (never stored)."""
    ctx = people_service.resolve_person(db, principal, person_id)
    people_service.get_person(ctx, person_id)
    items = kinship_service.compadrazgo_of(ctx, person_id)
    names = people_service.display_names(ctx, [item.person_id for item in items])
    return CompadrazgoList(
        items=[
            CompadrazgoItem(
                person_id=item.person_id,
                display_name=names.get(item.person_id, ""),
                relation=item.relation,
                sacrament=item.sacrament,
                label_es=item.label_es,
                label_en=item.label_en,
            )
            for item in items
        ]
    )


