"""Sources and citations."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, not_found
from family_history.models import Citation, Source
from family_history.models.enums import RevisionAction, Role, SourceType
from family_history.routers.schemas.evidence import Citation as CitationOut
from family_history.routers.schemas.evidence import CitationCreate, SourceCreate
from family_history.routers.schemas.evidence import Source as SourceOut
from family_history.services import audit
from family_history.services import names as name_rules
from family_history.services.access import DbSession, SpaceCtx, enter_space, user_scoped
from family_history.services.pagination import DEFAULT_LIMIT, MAX_LIMIT

router = APIRouter(prefix="/v1", tags=["sources"], responses=ERROR_RESPONSES)


def _out(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        space_id=source.family_space_id,
        type=SourceType(source.type),
        title=source.title,
        repository=source.repository,
        locator={k: str(v) for k, v in (source.locator or {}).items()},
        created_at=source.created_at,
    )


@router.post(
    "/spaces/{space_id}/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED
)
def create_source(body: SourceCreate, ctx: SpaceCtx) -> SourceOut:
    """A parish book (libro, foja, partida), a civil-registry act, an oral interview, ..."""
    ctx.require(Role.CONTRIBUTOR)
    source = Source(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        type=body.type.value,
        title=body.title,
        repository=body.repository,
        locator=dict(body.locator),
        created_by=ctx.sub,
    )
    ctx.db.add(source)
    audit.record(ctx, "source", source.id, RevisionAction.CREATE, body.model_dump(mode="json"))
    ctx.db.commit()
    return _out(source)


@router.get("/spaces/{space_id}/sources", response_model=list[SourceOut])
def list_sources(
    ctx: SpaceCtx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[SourceOut]:
    query = select(Source).where(Source.family_space_id == ctx.space_id)
    for token in name_rules.query_tokens(q or ""):
        query = query.where(Source.title.ilike(name_rules.like_pattern(token), escape="\\"))
    rows = ctx.db.scalars(query.order_by(Source.title, Source.id).limit(limit)).all()
    return [_out(row) for row in rows]


@router.post(
    "/sources/{source_id}/citations",
    response_model=CitationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_citation(
    source_id: uuid.UUID, body: CitationCreate, principal: EarlyAccessPrincipal, db: DbSession
) -> CitationOut:
    user_scoped(db, principal)
    space_id = db.scalar(select(Source.family_space_id).where(Source.id == source_id))
    if space_id is None:
        raise not_found("source_not_found", "Source not found.")
    ctx = enter_space(db, principal, space_id)
    ctx.require(Role.CONTRIBUTOR)
    citation = Citation(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        source_id=source_id,
        page=body.page,
        foja=body.foja,
        partida=body.partida,
        quality=body.quality,
        extracted_text=body.extracted_text,
        created_by=ctx.sub,
    )
    db.add(citation)
    audit.record(
        ctx,
        "citation",
        citation.id,
        RevisionAction.CREATE,
        {"source_id": source_id, **body.model_dump(mode="json", exclude={"extracted_text"})},
    )
    db.commit()
    return CitationOut.model_validate(citation)


@router.get("/sources/{source_id}/citations", response_model=list[CitationOut])
def list_citations(
    source_id: uuid.UUID, principal: EarlyAccessPrincipal, db: DbSession
) -> list[CitationOut]:
    user_scoped(db, principal)
    space_id = db.scalar(select(Source.family_space_id).where(Source.id == source_id))
    if space_id is None:
        raise not_found("source_not_found", "Source not found.")
    ctx = enter_space(db, principal, space_id)
    rows = ctx.db.scalars(
        select(Citation)
        .where(Citation.family_space_id == ctx.space_id, Citation.source_id == source_id)
        .order_by(Citation.created_at, Citation.id)
    ).all()
    return [CitationOut.model_validate(row) for row in rows]
