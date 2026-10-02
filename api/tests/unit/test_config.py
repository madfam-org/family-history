"""Settings: the auth-disabled guard, the fail-closed allowlist and derived values."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from family_history.config import Settings
from fh_testing import make_settings


@pytest.mark.parametrize("env", ["staging", "production"])
def test_auth_disabled_outside_local_and_test_fails_boot(env: str) -> None:
    with pytest.raises(ValidationError, match="FH_AUTH_DISABLED"):
        make_settings(FH_ENV=env, FH_AUTH_DISABLED="true")


@pytest.mark.parametrize("env", ["local", "test"])
def test_auth_disabled_is_honoured_in_dev(env: str) -> None:
    assert make_settings(FH_ENV=env, FH_AUTH_DISABLED="true").auth_disabled is True


def test_auth_disabled_guard_applies_to_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FH_ENV", "production")
    monkeypatch.setenv("FH_AUTH_DISABLED", "true")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_allowlist_is_case_insensitive_and_trimmed() -> None:
    settings = make_settings(FH_EARLY_ACCESS_ALLOWLIST=" User-Ana , Persona@Example.TEST ,, ")
    assert settings.early_access_allowlist == frozenset({"user-ana", "persona@example.test"})
    assert settings.is_allowlisted("USER-ANA")
    assert settings.is_allowlisted(None, "persona@example.test")
    assert not settings.is_allowlisted("user-otro", "otro@example.test")


@pytest.mark.parametrize("raw", ["", " ", ",,"])
def test_empty_allowlist_fails_closed(raw: str) -> None:
    settings = make_settings(FH_EARLY_ACCESS_ALLOWLIST=raw)
    assert settings.early_access_allowlist == frozenset()
    assert not settings.is_allowlisted("user-ana", "user-ana@example.test")


def test_cors_origins_are_split() -> None:
    settings = make_settings(FH_CORS_ORIGINS="http://localhost:3000, https://fh-app.madfam.io")
    assert settings.cors_origins == ["http://localhost:3000", "https://fh-app.madfam.io"]


def test_jwks_url_defaults_to_issuer_well_known() -> None:
    settings = make_settings(FH_JANUA_ISSUER="https://auth.madfam.io/")
    assert settings.janua_jwks_url == "https://auth.madfam.io/.well-known/jwks.json"
    override = make_settings(FH_JANUA_JWKS_URL="https://keys.example.test/jwks")
    assert override.janua_jwks_url == "https://keys.example.test/jwks"


def test_metrics_port_defaults() -> None:
    assert make_settings(FH_ENV="test").metrics_port is None
    assert make_settings(FH_ENV="local").metrics_port is None
    assert make_settings(FH_ENV="production").metrics_port == 9090
    assert make_settings(FH_ENV="staging", FH_METRICS_PORT="9100").metrics_port == 9100
    assert make_settings(FH_ENV="production", FH_METRICS_PORT="0").metrics_port is None
    with pytest.raises(ValidationError):
        make_settings(FH_METRICS_PORT="metrics")


def test_secrets_are_not_rendered() -> None:
    settings = make_settings(DATABASE_URL="postgresql://u:local-dev-only@db/fh")
    assert "local-dev-only" not in repr(settings)
