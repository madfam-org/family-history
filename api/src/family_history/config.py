"""Runtime settings for the API process.

Every variable here is named in docs/ARCHITECTURE.md §Environment. Values never live in the
repository; they arrive through the environment (or a local, git-ignored `.env`).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


DEV_ENVIRONMENTS = frozenset({Environment.LOCAL, Environment.TEST})

DEFAULT_JANUA_ISSUER = "https://auth.madfam.io"
DEFAULT_JANUA_AUDIENCE = "family-history-api"
DEFAULT_METRICS_PORT = 9090


class SettingsError(ValueError):
    """Raised when the environment describes an unsafe or impossible configuration."""


def _split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list | tuple | set | frozenset):
        return [str(part).strip() for part in value if str(part).strip()]
    raise SettingsError("expected a comma-separated string")


class Settings(BaseSettings):
    """Validated process configuration. Construct once via `get_settings()`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Unset means production: the safe default (no auth bypass, docs off, metrics on, HSTS).
    env: Environment = Field(default=Environment.PRODUCTION, alias="FH_ENV")

    database_url: SecretStr | None = Field(default=None, alias="DATABASE_URL")
    direct_database_url: SecretStr | None = Field(default=None, alias="DIRECT_DATABASE_URL")
    redis_url: SecretStr | None = Field(default=None, alias="REDIS_URL")

    janua_issuer: str = Field(default=DEFAULT_JANUA_ISSUER, alias="FH_JANUA_ISSUER")
    janua_audience: str = Field(default=DEFAULT_JANUA_AUDIENCE, alias="FH_JANUA_AUDIENCE")
    janua_jwks_url_override: str | None = Field(default=None, alias="FH_JANUA_JWKS_URL")
    jwks_timeout_seconds: float = 5.0
    jwks_cache_lifespan_seconds: float = 300.0
    jwt_leeway_seconds: int = 30

    auth_disabled: bool = Field(default=False, alias="FH_AUTH_DISABLED")

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="FH_CORS_ORIGINS"
    )
    early_access_allowlist: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset, alias="FH_EARLY_ACCESS_ALLOWLIST"
    )

    s3_endpoint: str | None = Field(default=None, alias="FH_S3_ENDPOINT")
    s3_bucket: str | None = Field(default=None, alias="FH_S3_BUCKET")
    s3_access_key_id: SecretStr | None = Field(default=None, alias="FH_S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr | None = Field(default=None, alias="FH_S3_SECRET_ACCESS_KEY")
    s3_region: str | None = Field(default=None, alias="FH_S3_REGION")

    sentry_dsn: SecretStr | None = Field(default=None, alias="FH_SENTRY_DSN")

    metrics_port_raw: str | None = Field(default=None, alias="FH_METRICS_PORT")

    waitlist_rate_limit: int = 5
    waitlist_rate_window_seconds: int = 600

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> list[str]:
        return _split_csv(value)

    @field_validator("early_access_allowlist", mode="before")
    @classmethod
    def _parse_allowlist(cls, value: Any) -> frozenset[str]:
        return frozenset(entry.casefold() for entry in _split_csv(value))

    @field_validator("janua_issuer")
    @classmethod
    def _strip_issuer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise SettingsError("FH_JANUA_ISSUER must not be empty")
        return value

    @model_validator(mode="after")
    def _guard_auth_disabled(self) -> Settings:
        if self.auth_disabled and self.env not in DEV_ENVIRONMENTS:
            raise SettingsError(
                "FH_AUTH_DISABLED=true is only honoured when FH_ENV is local or test"
            )
        # Fail early on a malformed metrics port instead of at listener start.
        _ = self.metrics_port
        return self

    @property
    def is_dev(self) -> bool:
        return self.env in DEV_ENVIRONMENTS

    @property
    def janua_jwks_url(self) -> str:
        if self.janua_jwks_url_override:
            return self.janua_jwks_url_override
        return self.janua_issuer.rstrip("/") + "/.well-known/jwks.json"

    @property
    def metrics_port(self) -> int | None:
        """Port of the separate Prometheus listener, or None when it is off.

        Unset: 9090 in staging and production, off in local and test. `0` or empty: off.
        """
        raw = self.metrics_port_raw
        if raw is None:
            return None if self.is_dev else DEFAULT_METRICS_PORT
        raw = raw.strip()
        if raw in ("", "0"):
            return None
        if not raw.isdigit() or not 0 < int(raw) < 65536:
            raise SettingsError("FH_METRICS_PORT must be a TCP port number")
        return int(raw)

    def is_allowlisted(self, *identities: str | None) -> bool:
        """True when any identity (subject or email) is on the early-access allowlist.

        An empty allowlist lets nobody in (fail closed).
        """
        if not self.early_access_allowlist:
            return False
        return any(
            identity is not None and identity.strip().casefold() in self.early_access_allowlist
            for identity in identities
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process settings, read from the environment once."""
    return Settings()


def request_settings(request: Request) -> Settings:
    """FastAPI dependency: the settings the running app was built with."""
    settings = getattr(request.app.state, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


AppSettings = Annotated[Settings, Depends(request_settings)]
