"""Assertions: facts with provenance. Append-only; status changes write a new version."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from family_history.auth import EarlyAccessPrincipal
from family_history.errors import ERROR_RESPONSES, not_found, unprocessable
from family_history.models import Assertion
from family_history.models.enums import AssertionStatus, RevisionAction, Role, SubjectType
from family_history.routers.schemas.evidence import Assertion as AssertionOut
from family_history.routers.schemas.evidence import (
    AssertionCitationLink,
    AssertionCreate,
    AssertionStatusChange,
)
from family_history.services import audit
from family_history.services import evidence as evidence_service
from family_history.services.access import (
    DbSession,
    SpaceContext,
    SpaceCtx,
    enter_space,
    user_scoped,
)
from family_history.services.living import recompute_for_subject
from family_history.services.privacy import default_field_sensitivity

router = APIRouter(prefix="/v1", tags=["assertions"], responses=ERROR_RESPONSES)


def _enter_for_assertion(
    db: DbSession, principal: EarlyAccessPrincipal, assertion_id: uuid.UUID
) -> SpaceContext:
    user_scoped(db, principal)
    space_id = db.scalar(select(Assertion.family_space_id).where(Assertion.id == assertion_id))
    if space_id is None:
        raise not_found("assertion_not_found", "Assertion not found.")
    return enter_space(db, principal, space_id)


@router.get("/spaces/{space_id}/assertions", response_model=list[AssertionOut])
def list_assertions(
    ctx: SpaceCtx,
    subject_type: SubjectType,
    subject_id: uuid.UUID,
    include_history: bool = False,
) -> list[AssertionOut]:
    """Assertions about one subject. By default only the current version of each."""
    base = select(Assertion) if include_history else evidence_service.current_assertions()
    rows = ctx.db.scalars(
        base.where(
            Assertion.family_space_id == ctx.space_id,
            Assertion.subject_type == subject_type.value,
            Assertion.subject_id == subject_id,
        ).order_by(Assertion.created_at, Assertion.id)
    ).all()
    return [evidence_service.to_out(row) for row in evidence_service.visible_assertions(ctx, rows)]


@router.post(
    "/spaces/{space_id}/assertions",
    response_model=AssertionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_assertion(body: AssertionCreate, ctx: SpaceCtx) -> AssertionOut:
    """Contributors add assertions. Accepting one needs a citation; AI output only suggests."""
    ctx.require(Role.CONTRIBUTOR)
    if body.status is AssertionStatus.RETRACTED:
        raise unprocessable("invalid_status", "A new assertion cannot start retracted.")
    if body.status is not AssertionStatus.SUGGESTED:
        ctx.require(Role.EDITOR)
    if body.status is AssertionStatus.ACCEPTED and not body.citation_ids:
        raise unprocessable(
            "citation_required", "Accepting an assertion needs at least one citation."
        )
    evidence_service.require_subject(ctx, body.subject_type, body.subject_id)
    citation_ids = evidence_service.require_citations(ctx, body.citation_ids)
    sensitivity = body.sensitivity or default_field_sensitivity(body.field)
    assertion = Assertion(
        id=uuid.uuid4(),
        family_space_id=ctx.space_id,
        subject_type=body.subject_type.value,
        subject_id=body.subject_id,
        field=body.field,
        value=body.value,
        status=body.status.value,
        asserted_by=ctx.sub,
        citation_ids=citation_ids,
        sensitivity=sensitivity.value if sensitivity else None,
    )
    ctx.db.add(assertion)
    audit.record(
        ctx,
        "assertion",
        assertion.id,
        RevisionAction.CREATE,
        {
            "subject_type": assertion.subject_type,
            "subject_id": assertion.subject_id,
            "field": assertion.field,
            "status": assertion.status,
            "citation_ids": citation_ids,
        },
    )
    # A cited death, burial or cremation is evidence: the principals' living status may change.
    recompute_for_subject(ctx, assertion.subject_type, assertion.subject_id)
    ctx.db.commit()
    return evidence_service.to_out(assertion)


@router.post(
    "/assertions/{assertion_id}/status",
    response_model=AssertionOut,
    status_code=status.HTTP_201_CREATED,
)
def change_status(
    assertion_id: uuid.UUID,
    body: AssertionStatusChange,
    principal: EarlyAccessPrincipal,
    db: DbSession,
) -> AssertionOut:
    """Write a new version with the new status. Editors decide; accepting needs a citation."""
    ctx = _enter_for_assertion(db, principal, assertion_id)
    previous = evidence_service.get_current(ctx, assertion_id)
    retracting_own = body.status is AssertionStatus.RETRACTED and previous.asserted_by == ctx.sub
    if not retracting_own:
        ctx.require(Role.EDITOR)
    extra = evidence_service.require_citations(ctx, body.citation_ids)
    citation_ids = list(dict.fromkeys([*previous.citation_ids, *extra]))
    row = evidence_service.append_version(
        ctx, previous, status=body.status, citation_ids=citation_ids
    )
    recompute_for_subject(ctx, row.subject_type, row.subject_id)
    db.commit()
    return evidence_service.to_out(row)


@router.post(
    "/assertions/{assertion_id}/citations",
    response_model=AssertionOut,
    status_code=status.HTTP_201_CREATED,
)
def link_citations(
    assertion_id: uuid.UUID,
    body: AssertionCitationLink,
    principal: EarlyAccessPrincipal,
    db: DbSession,
) -> AssertionOut:
    """Link citations to an assertion (a new version with the same status)."""
    ctx = _enter_for_assertion(db, principal, assertion_id)
    ctx.require(Role.CONTRIBUTOR)
    previous = evidence_service.get_current(ctx, assertion_id)
    added = evidence_service.require_citations(ctx, body.citation_ids)
    citation_ids = list(dict.fromkeys([*previous.citation_ids, *added]))
    row = evidence_service.append_version(
        ctx, previous, status=AssertionStatus(previous.status), citation_ids=citation_ids
    )
    recompute_for_subject(ctx, row.subject_type, row.subject_id)
    db.commit()
    return evidence_service.to_out(row)
