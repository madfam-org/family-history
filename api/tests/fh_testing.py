"""Test helpers shared by the unit and Postgres suites. Every identity here is synthetic."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

from jwt import PyJWKClient

from family_history.config import Settings

ISSUER = "https://auth.example.test"
AUDIENCE = "family-history-api"
KID = "test-key-1"

ALLOWED_SUBS = ("user-ana", "user-beto", "user-carla", "user-dario")
ALLOWED_EMAIL = "persona.invitada@example.test"


class StubJWKClient(PyJWKClient):
    """The real PyJWKClient key selection, with the network fetch replaced."""

    def __init__(self, jwks: dict[str, Any]) -> None:
        super().__init__("https://auth.example.test/.well-known/jwks.json", cache_keys=True)
        self._jwks = jwks
        self.fetches = 0

    def fetch_data(self) -> Any:
        self.fetches += 1
        return self._jwks


TokenFactory = Callable[..., str]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unsigned_token(claims: dict[str, Any]) -> str:
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    return f"{header}.{_b64(json.dumps(claims).encode())}."


def hs256_token(claims: dict[str, Any], secret: bytes) -> str:
    """An HS256 token signed with `secret` (e.g. the RSA public key: key confusion)."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = _b64(json.dumps(claims).encode())
    signature = hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "FH_ENV": "test",
        "FH_JANUA_ISSUER": ISSUER,
        "FH_JANUA_AUDIENCE": AUDIENCE,
        "FH_EARLY_ACCESS_ALLOWLIST": ",".join((*ALLOWED_SUBS, ALLOWED_EMAIL)),
        "FH_CORS_ORIGINS": "http://localhost:3000",
        "DATABASE_URL": None,
    }
    values.update(overrides)
    return Settings.model_validate(values)
