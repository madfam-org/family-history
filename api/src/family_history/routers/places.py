"""Places: a time-aware hierarchy (país → estado → municipio → localidad, parroquia, hacienda)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from family_history.errors import ERROR_RESPONSES
from family_history.models import Place
from family_history.models.enums import PlaceKind, RevisionAction, Role
from family_history.routers.schemas.events import Place as PlaceOut
from family_history.routers.schemas.events import PlaceCreate
from family_history.services import audit
from family_history.services import names as name_rules
from family_history.services.access import SpaceCtx
from family_history.services.events import require_place
from family_history.services.pagination import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/v1", tags=["places"], responses=ERROR_RESPONSES)


def _out(place: Place) -> PlaceOut:
    return PlaceOut(
        id=place.id,
        space_id=place.family_space_id,
        name=place.name,
        kind=PlaceKind(place.kind),
        parent_id=place.parent_id,
        valid_from=place.valid_from,
        valid_to=place.valid_to,
        inegi_code=place.inegi_code,
        created_at=place.created_at,
    )


@router.post(
    "/spaces/{space_id}/places", response_model=PlaceOut, status_code=status.HTTP_201_CREATED
)
def create_place(body: PlaceCreate, ctx: SpaceCtx) -> PlaceOut:
    ctx.require(Role.CONTRIBUTOR)
    require_place(ctx, body.parent_id)
    place = Place(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        name=body.name,
        kind=body.kind.value,
        parent_id=body.parent_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        inegi_code=body.inegi_code,
        search_text=name_rules.normalize(body.name),
        created_by=ctx.sub,
    )
    ctx.db.add(place)
    audit.record(ctx, "place", place.id, RevisionAction.CREATE, body.model_dump(mode="json"))
    ctx.db.commit()
    return _out(place)


@router.get("/spaces/{space_id}/places", response_model=list[PlaceOut])
def search_places(
    ctx: SpaceCtx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: PlaceKind | None = None,
    parent_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[PlaceOut]:
    """Places in the space; `q` matches the name ignoring case and accents."""
    query = select(Place).where(Place.family_space_id == ctx.space_id)
    for token in name_rules.search_tokens(q or ""):
        query = query.where(Place.search_text.like(name_rules.like_pattern(token), escape="\\"))
    if kind is not None:
        query = query.where(Place.kind == kind.value)
    if parent_id is not None:
        query = query.where(Place.parent_id == parent_id)
    rows = ctx.db.scalars(query.order_by(Place.search_text, Place.id).limit(limit)).all()
    return [_out(row) for row in rows]
