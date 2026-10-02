"""Janua bearer-token verification and the request principal.

Tokens are RS256 JWTs signed by Janua. Keys come from the issuer's JWKS through a cached
`PyJWKClient` with a short network timeout. Only RS256 is accepted: HS256 (key-confusion) and
`none` are rejected before any key lookup. Issuer, audience (`family-history-api`) and expiry are
enforced with a small leeway.

When `FH_AUTH_DISABLED=true` (honoured only in local and test, see `config.py`), every request
runs as a fixed synthetic principal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from family_history.config import Settings, get_settings
from family_history.errors import APIError
from family_history.metrics import AUTH_FAILURES

logger = logging.getLogger("family_history.auth")

ALLOWED_ALGORITHMS = ("RS256",)

SYNTHETIC_SUB = "synthetic-local-user"
SYNTHETIC_EMAIL = "persona.sintetica@example.test"
SYNTHETIC_NAME = "Persona Sintética"


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    sub: str
    email: str | None = None
    name: str | None = None
    orgs: tuple[str, ...] = field(default_factory=tuple)
    email_verified: bool | None = None
    synthetic: bool = False


class SigningKeyResolver(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


def _unauthorized(code: str, message: str) -> APIError:
    AUTH_FAILURES.labels(code=code).inc()
    return APIError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def _parse_orgs(raw: Any) -> tuple[str, ...]:
    """Janua's `orgs` claim: a list of organization ids, or of objects carrying an `id`."""
    if not isinstance(raw, list):
        return ()
    orgs: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            orgs.append(item)
        elif isinstance(item, dict):
            org_id = item.get("id") or item.get("org_id")
            if isinstance(org_id, str) and org_id:
                orgs.append(org_id)
    return tuple(orgs)


def _optional_str(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    return value if isinstance(value, str) and value else None


class TokenVerifier:
    """Verifies Janua access tokens. One instance per process (it owns the JWKS cache)."""

    def __init__(self, settings: Settings, key_resolver: SigningKeyResolver | None = None):
        self._issuer = settings.janua_issuer
        self._audience = settings.janua_audience
        self._leeway = settings.jwt_leeway_seconds
        self._keys: SigningKeyResolver = key_resolver or PyJWKClient(
            settings.janua_jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=settings.jwks_cache_lifespan_seconds,
            timeout=settings.jwks_timeout_seconds,
        )

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise _unauthorized("invalid_token", "The bearer token is malformed.") from exc
        if header.get("alg") not in ALLOWED_ALGORITHMS:
            raise _unauthorized("invalid_token", "The token algorithm is not accepted.")

        try:
            signing_key = self._keys.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            logger.warning("jwks fetch failed", extra={"error_type": type(exc).__name__})
            raise APIError(
                503, "auth_unavailable", "Token keys are temporarily unavailable."
            ) from exc
        except jwt.PyJWTError as exc:
            raise _unauthorized("invalid_token", "The token signing key is unknown.") from exc

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=signing_key.key if hasattr(signing_key, "key") else signing_key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise _unauthorized("token_expired", "The bearer token has expired.") from exc
        except jwt.PyJWTError as exc:
            raise _unauthorized("invalid_token", "The bearer token is not valid.") from exc

        sub = _optional_str(claims, "sub")
        if sub is None:
            raise _unauthorized("invalid_token", "The bearer token has no subject.")
        verified = claims.get("email_verified")
        return Principal(
            sub=sub,
            email=_optional_str(claims, "email"),
            name=_optional_str(claims, "name"),
            orgs=_parse_orgs(claims.get("orgs")),
            email_verified=verified if isinstance(verified, bool) else None,
        )


def synthetic_principal() -> Principal:
    return Principal(
        sub=SYNTHETIC_SUB,
        email=SYNTHETIC_EMAIL,
        name=SYNTHETIC_NAME,
        email_verified=True,
        synthetic=True,
    )


def has_early_access(principal: Principal, settings: Settings) -> bool:
    """Allowlisted by subject, or by email unless Janua says the email is unverified."""
    if principal.synthetic and settings.auth_disabled and settings.is_dev:
        return True
    email = principal.email if principal.email_verified is not False else None
    return settings.is_allowlisted(principal.sub, email)


def get_verifier(request: Request) -> TokenVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    if not isinstance(verifier, TokenVerifier):
        raise APIError(503, "auth_unavailable", "Token verification is not configured.")
    return verifier


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header:
        raise _unauthorized("missing_token", "A bearer token is required.")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("invalid_token", "The Authorization header must be a bearer token.")
    return token


def current_principal(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> Principal:
    """Authenticate the request. Does not enforce early access (see `require_early_access`)."""
    if settings.auth_disabled and settings.is_dev:
        return synthetic_principal()
    token = _bearer_token(request)
    return get_verifier(request).verify(token)


def require_early_access(
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if not has_early_access(principal, settings):
        AUTH_FAILURES.labels(code="early_access_required").inc()
        raise APIError(403, "early_access_required", "Early access is required.")
    return principal


AuthenticatedPrincipal = Annotated[Principal, Depends(current_principal)]
EarlyAccessPrincipal = Annotated[Principal, Depends(require_early_access)]
