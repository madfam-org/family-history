"""Relationships: the parent–child and union edges of the family graph."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, conflict, not_found
from family_history.models import Relationship
from family_history.models.enums import RevisionAction, Role
from family_history.routers.schemas.events import Relationship as RelationshipOut
from family_history.routers.schemas.events import RelationshipCreate
from family_history.services import audit
from family_history.services.access import DbSession, SpaceCtx, enter_space, user_scoped
from family_history.services.events import require_people
from family_history.services.people import relationships_out

router = APIRouter(prefix="/v1", tags=["relationships"], responses=ERROR_RESPONSES)


@router.post(
    "/spaces/{space_id}/relationships",
    response_model=RelationshipOut,
    status_code=status.HTTP_201_CREATED,
)
def create_relationship(body: RelationshipCreate, ctx: SpaceCtx) -> RelationshipOut:
    """For `parent_child`, `from_person_id` is the parent and `to_person_id` the child."""
    ctx.require(Role.CONTRIBUTOR)
    require_people(ctx, [body.from_person_id, body.to_person_id])
    duplicate = ctx.db.scalar(
        select(Relationship.id).where(
            Relationship.family_space_id == ctx.space_id,
            Relationship.type == body.type.value,
            Relationship.from_person_id == body.from_person_id,
            Relationship.to_person_id == body.to_person_id,
            Relationship.pedigree.is_not_distinct_from(
                body.pedigree.value if body.pedigree else None
            ),
            Relationship.partner_status.is_not_distinct_from(
                body.partner_status.value if body.partner_status else None
            ),
        )
    )
    if duplicate is not None:
        raise conflict("relationship_exists", "This relationship already exists.")
    relationship = Relationship(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        type=body.type.value,
        from_person_id=body.from_person_id,
        to_person_id=body.to_person_id,
        pedigree=body.pedigree.value if body.pedigree else None,
        partner_status=body.partner_status.value if body.partner_status else None,
        created_by=ctx.sub,
    )
    ctx.db.add(relationship)
    audit.record(
        ctx,
        "relationship",
        relationship.id,
        RevisionAction.CREATE,
        body.model_dump(mode="json"),
    )
    ctx.db.commit()
    return relationships_out(ctx, [relationship])[0]


@router.delete(
    "/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_relationship(
    relationship_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> Response:
    user_scoped(db, principal)
    space_id = db.scalar(
        select(Relationship.family_space_id).where(Relationship.id == relationship_id)
    )
    if space_id is None:
        raise not_found("relationship_not_found", "Relationship not found.")
    ctx = enter_space(db, principal, space_id)
    relationship = db.get(Relationship, relationship_id)
    if relationship is None or not relationships_out(ctx, [relationship]):
        raise not_found("relationship_not_found", "Relationship not found.")
    ctx.require(Role.EDITOR)
    audit.record(
        ctx,
        "relationship",
        relationship.id,
        RevisionAction.DELETE,
        {
            "type": relationship.type,
            "from_person_id": relationship.from_person_id,
            "to_person_id": relationship.to_person_id,
            "pedigree": relationship.pedigree,
            "partner_status": relationship.partner_status,
        },
    )
    db.delete(relationship)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
