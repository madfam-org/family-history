"""Janua token verification: RS256 only, issuer, audience, expiry and early access."""

from __future__ import annotations

import time
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from family_history.app import create_app
from family_history.auth import (
    EarlyAccessPrincipal,
    TokenVerifier,
    has_early_access,
    synthetic_principal,
)
from family_history.errors import APIError
from fh_testing import (
    ALLOWED_EMAIL,
    AUDIENCE,
    ISSUER,
    StubJWKClient,
    TokenFactory,
    hs256_token,
    make_settings,
    unsigned_token,
)


@pytest.fixture
def verifier(jwk_client: StubJWKClient) -> TokenVerifier:
    return TokenVerifier(make_settings(), key_resolver=jwk_client)


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "user-ana", "iat": now, "exp": now + 600}
    claims.update(overrides)
    return claims


def _code(exc: pytest.ExceptionInfo[APIError]) -> tuple[int, str]:
    return exc.value.status_code, exc.value.code


def test_valid_token_yields_principal(verifier: TokenVerifier, make_token: TokenFactory) -> None:
    token = make_token("user-ana", orgs=["org-1", {"id": "org-2"}, 7])
    principal = verifier.verify(token)
    assert principal.sub == "user-ana"
    assert principal.email == "user-ana@example.test"
    assert principal.name == "Persona Sintética"
    assert principal.orgs == ("org-1", "org-2")


def test_jwks_is_cached(
    verifier: TokenVerifier, make_token: TokenFactory, jwk_client: StubJWKClient
) -> None:
    for _ in range(3):
        verifier.verify(make_token())
    assert jwk_client.fetches == 1


def test_expired_token(verifier: TokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(make_token(exp_in=-3600))
    assert _code(exc) == (401, "token_expired")


def test_small_clock_skew_is_tolerated(verifier: TokenVerifier, make_token: TokenFactory) -> None:
    assert verifier.verify(make_token(exp_in=-5)).sub == "user-ana"


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "another-api"},
        {"iss": "https://evil.example.test"},
        {"aud": None},
        {"exp": None},
    ],
)
def test_wrong_or_missing_claims(
    verifier: TokenVerifier, make_token: TokenFactory, overrides: dict[str, Any]
) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(make_token(**overrides))
    assert _code(exc) == (401, "invalid_token")


def test_signature_from_another_key(
    verifier: TokenVerifier, make_token: TokenFactory, other_rsa_key: rsa.RSAPrivateKey
) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(make_token(key=other_rsa_key))
    assert _code(exc) == (401, "invalid_token")


def test_unknown_kid(verifier: TokenVerifier, make_token: TokenFactory) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(make_token(kid="rotated-away"))
    assert _code(exc) == (401, "invalid_token")


def test_hs256_key_confusion_is_rejected(verifier: TokenVerifier, public_pem: bytes) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(hs256_token(_claims(), public_pem))
    assert _code(exc) == (401, "invalid_token")


def test_alg_none_is_rejected(verifier: TokenVerifier) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(unsigned_token(_claims()))
    assert _code(exc) == (401, "invalid_token")


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_malformed_tokens(verifier: TokenVerifier, token: str) -> None:
    with pytest.raises(APIError) as exc:
        verifier.verify(token)
    assert exc.value.status_code == 401


def test_early_access_by_sub_or_verified_email(
    verifier: TokenVerifier, make_token: TokenFactory
) -> None:
    settings = make_settings()
    assert has_early_access(verifier.verify(make_token("user-ana")), settings)
    by_email = verifier.verify(make_token("user-zeta", email=ALLOWED_EMAIL.upper()))
    assert has_early_access(by_email, settings)
    unverified = verifier.verify(make_token("user-zeta", email=ALLOWED_EMAIL, email_verified=False))
    assert not has_early_access(unverified, settings)
    assert not has_early_access(verifier.verify(make_token("user-zeta")), settings)


def test_synthetic_principal_needs_auth_disabled_in_dev() -> None:
    principal = synthetic_principal()
    assert has_early_access(principal, make_settings(FH_AUTH_DISABLED="true"))
    assert not has_early_access(principal, make_settings(FH_EARLY_ACCESS_ALLOWLIST=""))


# HTTP layer -------------------------------------------------------------------------------


@pytest.fixture
def client(jwk_client: StubJWKClient) -> TestClient:
    return TestClient(create_app(make_settings(), key_resolver=jwk_client))


def test_missing_token_is_401_with_envelope(client: TestClient) -> None:
    response = client.get("/v1/spaces")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "missing_token", "message": "A bearer token is required."}
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_non_bearer_scheme(client: TestClient) -> None:
    response = client.get("/v1/spaces", headers={"Authorization": "Basic abc"})
    assert response.json()["error"]["code"] == "invalid_token"


def test_me_without_early_access(client: TestClient, make_token: TokenFactory) -> None:
    token = make_token("user-zeta")
    response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {
        "sub": "user-zeta",
        "email": "user-zeta@example.test",
        "name": "Persona Sintética",
        "early_access": False,
        "spaces": [],
    }


def test_early_access_required_on_v1(client: TestClient, make_token: TokenFactory) -> None:
    token = make_token("user-zeta")
    response = client.get("/v1/spaces", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "early_access_required"


def test_empty_allowlist_lets_nobody_in(
    jwk_client: StubJWKClient, make_token: TokenFactory
) -> None:
    app = create_app(make_settings(FH_EARLY_ACCESS_ALLOWLIST=""), key_resolver=jwk_client)
    response = TestClient(app).get(
        "/v1/spaces", headers={"Authorization": f"Bearer {make_token('user-ana')}"}
    )
    assert response.json()["error"]["code"] == "early_access_required"


def test_allowlisted_user_reaches_the_database_layer(
    client: TestClient, make_token: TokenFactory
) -> None:
    response = client.get(
        "/v1/spaces", headers={"Authorization": f"Bearer {make_token('user-ana')}"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_auth_disabled_uses_synthetic_principal(jwk_client: StubJWKClient) -> None:
    app = create_app(
        make_settings(FH_AUTH_DISABLED="true", FH_EARLY_ACCESS_ALLOWLIST=""),
        key_resolver=jwk_client,
    )

    @app.get("/probe")
    def probe(principal: EarlyAccessPrincipal) -> dict[str, str | None]:
        return {"sub": principal.sub, "email": principal.email}

    body = TestClient(app).get("/probe").json()
    assert body == {"sub": "synthetic-local-user", "email": "persona.sintetica@example.test"}


def test_auth_disabled_is_ignored_without_the_flag(jwk_client: StubJWKClient) -> None:
    app = create_app(make_settings(), key_resolver=jwk_client)

    @app.get("/probe")
    def probe(principal: EarlyAccessPrincipal) -> dict[str, str]:
        return {"sub": principal.sub}

    assert TestClient(app).get("/probe").status_code == 401
