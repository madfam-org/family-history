"""The public waitlist: no auth, rate limited, and silent about existing emails."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.dialects.postgresql import insert

from family_history.config import AppSettings
from family_history.errors import ERROR_RESPONSES, APIError, unprocessable
from family_history.metrics import WAITLIST_SIGNUPS
from family_history.models import WaitlistEntry
from family_history.models.base import utcnow
from family_history.routers.schemas.waitlist import WaitlistAccepted, WaitlistRequest
from family_history.services.access import DbSession
from family_history.services.ratelimit import AddressHasher, SlidingWindowLimiter

logger = logging.getLogger("family_history.waitlist")

router = APIRouter(prefix="/v1", tags=["waitlist"], responses=ERROR_RESPONSES)


def client_address(request: Request) -> str:
    """The caller's address. Behind the Cloudflare tunnel the edge sets `CF-Connecting-IP`
    (and overwrites any client-supplied value); otherwise use the socket peer."""
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if forwarded:
        return forwarded[:64]
    return request.client.host if request.client else "unknown"


def get_limiter(request: Request) -> SlidingWindowLimiter:
    limiter = getattr(request.app.state, "waitlist_limiter", None)
    if not isinstance(limiter, SlidingWindowLimiter):
        raise APIError(503, "rate_limiter_unavailable", "The waitlist is not available.")
    return limiter


def get_hasher(request: Request) -> AddressHasher:
    hasher = getattr(request.app.state, "address_hasher", None)
    if not isinstance(hasher, AddressHasher):
        raise APIError(503, "rate_limiter_unavailable", "The waitlist is not available.")
    return hasher


def require_waitlist_open(settings: AppSettings) -> None:
    """Closed unless `FH_WAITLIST_ENABLED`: nothing is stored before the reviewed privacy notice
    ships. Runs before validation and rate limiting, so a closed waitlist reads no input."""
    if not settings.waitlist_enabled:
        WAITLIST_SIGNUPS.labels(outcome="closed").inc()
        raise APIError(404, "waitlist_closed", "The waitlist is not open.")


def enforce_rate_limit(
    request: Request,
    limiter: Annotated[SlidingWindowLimiter, Depends(get_limiter)],
    hasher: Annotated[AddressHasher, Depends(get_hasher)],
    settings: AppSettings,
) -> str:
    ip_hash = hasher(client_address(request))
    if not limiter.allow(ip_hash):
        WAITLIST_SIGNUPS.labels(outcome="rate_limited").inc()
        raise APIError(
            429,
            "rate_limited",
            "Too many requests. Try again later.",
            headers={"Retry-After": str(settings.waitlist_rate_window_seconds)},
        )
    return ip_hash


@router.post(
    "/waitlist",
    response_model=WaitlistAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_waitlist_open)],
)
def join_waitlist(
    body: WaitlistRequest,
    ip_hash: Annotated[str, Depends(enforce_rate_limit)],
    db: DbSession,
    settings: AppSettings,
) -> WaitlistAccepted:
    """Join the waitlist. `404 waitlist_closed` until the waitlist is opened with a reviewed
    privacy notice. Once open, always `202` for a valid request, whether or not the email was
    already on the list. Consent to the current privacy notice (`aviso_version`) is required."""
    if not body.consent:
        WAITLIST_SIGNUPS.labels(outcome="no_consent").inc()
        raise unprocessable("consent_required", "Consent to the privacy notice is required.")
    if body.aviso_version != settings.aviso_version:
        WAITLIST_SIGNUPS.labels(outcome="aviso_mismatch").inc()
        raise unprocessable(
            "aviso_version_mismatch", "Consent must refer to the current privacy notice."
        )
    now = utcnow()
    statement = (
        insert(WaitlistEntry)
        .values(
            id=uuid.uuid4(),
            email=body.email,
            locale=body.locale,
            consent_at=now,
            aviso_version=body.aviso_version,
            created_at=now,
            ip_hash=ip_hash,
        )
        .on_conflict_do_nothing()
    )
    db.execute(statement)
    db.commit()
    WAITLIST_SIGNUPS.labels(outcome="accepted").inc()
    logger.info("waitlist request accepted", extra={"locale": body.locale})
    return WaitlistAccepted()
