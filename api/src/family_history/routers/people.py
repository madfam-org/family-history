"""People: list and search, create with names, read, patch and soft delete."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, unprocessable
from family_history.models import Person
from family_history.models.base import utcnow
from family_history.models.enums import LivingStatus, RevisionAction, Role, Visibility
from family_history.routers.schemas.people import Person as PersonOut
from family_history.routers.schemas.people import PersonCreate, PersonPage, PersonPatch
from family_history.services import audit
from family_history.services import people as people_service
from family_history.services.access import DbSession, SpaceCtx
from family_history.services.pagination import DEFAULT_LIMIT, MAX_LIMIT
from family_history.services.privacy import treated_as_living

router = APIRouter(prefix="/v1", tags=["people"], responses=ERROR_RESPONSES)


def _check_visibility(visibility: Visibility, living_status: str) -> None:
    if visibility is Visibility.PUBLIC_MEMORIAL and treated_as_living(living_status):
        raise unprocessable(
            "living_person_not_public",
            "A living person cannot be public; record a death event first.",
        )


@router.get("/spaces/{space_id}/people", response_model=PersonPage)
def list_people(
    ctx: SpaceCtx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
) -> PersonPage:
    """People in the space, ordered by surname. `q` matches any name part, ignoring accents."""
    return people_service.list_people(ctx, q, limit, cursor)


@router.post(
    "/spaces/{space_id}/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED
)
def create_person(body: PersonCreate, ctx: SpaceCtx) -> PersonOut:
    ctx.require(Role.CONTRIBUTOR)
    # A new person has no death event yet, so they start as living.
    _check_visibility(body.visibility, LivingStatus.LIVING.value)
    person = Person(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        sex=body.sex.value,
        visibility=body.visibility.value,
        living_status=LivingStatus.LIVING.value,
        created_by=ctx.sub,
    )
    people_service.set_names(person, body.names)
    ctx.db.add(person)
    audit.record(
        ctx,
        "person",
        person.id,
        RevisionAction.CREATE,
        {
            "sex": person.sex,
            "visibility": person.visibility,
            "names": people_service.names_snapshot(person),
        },
    )
    ctx.db.commit()
    return people_service.detail(ctx, person)


@router.get("/people/{person_id}", response_model=PersonOut)
def get_person(person_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession) -> PersonOut:
    """A person with names, events, relationships and citations."""
    ctx = people_service.resolve_person(db, principal, person_id)
    return people_service.detail(ctx, people_service.get_person(ctx, person_id))


@router.patch("/people/{person_id}", response_model=PersonOut)
def patch_person(
    person_id: uuid.UUID, body: PersonPatch, principal: EarlyAccessPrincipal, db: DbSession
) -> PersonOut:
    ctx = people_service.resolve_person(db, principal, person_id)
    ctx.require(Role.EDITOR)
    person = people_service.get_person(ctx, person_id)
    before = {
        "sex": person.sex,
        "visibility": person.visibility,
        "names": people_service.names_snapshot(person),
    }
    if body.sex is not None:
        person.sex = body.sex.value
    if body.visibility is not None:
        _check_visibility(body.visibility, person.living_status)
        person.visibility = body.visibility.value
    if body.names is not None:
        people_service.set_names(person, body.names)
    after = {
        "sex": person.sex,
        "visibility": person.visibility,
        "names": people_service.names_snapshot(person),
    }
    diff = audit.changes(before, after)
    if diff:
        person.updated_at = utcnow()
        audit.record(ctx, "person", person.id, RevisionAction.UPDATE, diff)
    ctx.db.commit()
    return people_service.detail(ctx, person)


@router.delete(
    "/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_person(person_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession) -> Response:
    """Soft delete: the person disappears from every read; the revision keeps the record."""
    ctx = people_service.resolve_person(db, principal, person_id)
    ctx.require(Role.EDITOR)
    person = people_service.get_person(ctx, person_id)
    person.deleted_at = utcnow()
    audit.record(
        ctx,
        "person",
        person.id,
        RevisionAction.DELETE,
        {"deleted_at": person.deleted_at, "names": people_service.names_snapshot(person)},
    )
    ctx.db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
