"""Shared fixtures: locally generated RSA keys, a stubbed JWKS and token factories.

Tests never call the real Janua. Every identity here is synthetic.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from family_history.config import Settings
from fh_testing import AUDIENCE, ISSUER, KID, StubJWKClient, TokenFactory, make_settings


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("FH_TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="FH_TEST_DATABASE_URL is not set")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def public_pem(rsa_key: rsa.RSAPrivateKey) -> bytes:
    return rsa_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


@pytest.fixture(scope="session")
def jwks(rsa_key: rsa.RSAPrivateKey) -> dict[str, Any]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


@pytest.fixture
def jwk_client(jwks: dict[str, Any]) -> StubJWKClient:
    return StubJWKClient(jwks)


@pytest.fixture
def make_token(rsa_key: rsa.RSAPrivateKey) -> TokenFactory:
    def factory(
        sub: str = "user-ana",
        *,
        key: rsa.RSAPrivateKey | None = None,
        kid: str = KID,
        exp_in: int = 600,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": sub,
            "iat": now,
            "exp": now + exp_in,
            "email": f"{sub}@example.test",
            "email_verified": True,
            "name": "Persona Sintética",
            "scope": "openid fh:read fh:write",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, key or rsa_key, algorithm="RS256", headers={"kid": kid})

    return factory


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    return make_settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ambient FH_* variables must not leak into settings built by tests."""
    for name in list(os.environ):
        if name.startswith("FH_") and not name.startswith("FH_TEST_"):
            monkeypatch.delenv(name, raising=False)
    for name in ("DATABASE_URL", "DIRECT_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    yield
