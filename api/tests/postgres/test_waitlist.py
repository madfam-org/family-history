"""The public waitlist."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from family_history.app import create_app
from family_history.db.engine import Database
from fh_testing import StubJWKClient, make_settings

pytestmark = pytest.mark.postgres

BODY = {"email": "Sintetico.Uno@Example.TEST", "consent": True, "aviso_version": "2026-10"}
OPEN = {"FH_WAITLIST_ENABLED": "true", "FH_AVISO_VERSION": "2026-10"}


@pytest.fixture
def client(engine: Engine, database: Database, jwk_client: StubJWKClient) -> Iterator[TestClient]:
    """The waitlist opened with a reviewed notice. It is closed by default (see below)."""
    app = create_app(make_settings(**OPEN), database=database, key_resolver=jwk_client)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def closed_client(
    engine: Engine, database: Database, jwk_client: StubJWKClient
) -> Iterator[TestClient]:
    app = create_app(make_settings(), database=database, key_resolver=jwk_client)
    with TestClient(app) as test_client:
        yield test_client


def _stored(engine: Engine) -> list[tuple[str, str, str | None]]:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.waitlist_relay', 'on', true)"))
        rows = conn.execute(
            text("SELECT email, aviso_version, ip_hash FROM waitlist_entry ORDER BY email")
        ).all()
    return [tuple(row) for row in rows]  # type: ignore[misc]


def test_closed_by_default_and_stores_nothing(closed_client: TestClient, engine: Engine) -> None:
    response = closed_client.post("/v1/waitlist", json=BODY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "waitlist_closed"
    assert _stored(engine) == []


def test_consent_must_name_the_current_notice(client: TestClient, engine: Engine) -> None:
    response = client.post("/v1/waitlist", json={**BODY, "aviso_version": "2025-01"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "aviso_version_mismatch"
    assert _stored(engine) == []


def test_join_is_public_and_accepted(client: TestClient, engine: Engine) -> None:
    response = client.post("/v1/waitlist", json=BODY)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    [(email, aviso, ip_hash)] = _stored(engine)
    assert email == "Sintetico.Uno@example.test"
    assert aviso == "2026-10"
    assert ip_hash and len(ip_hash) == 64


def test_duplicate_is_indistinguishable(client: TestClient, engine: Engine) -> None:
    first = client.post("/v1/waitlist", json=BODY)
    again = client.post("/v1/waitlist", json={**BODY, "email": "sintetico.uno@example.test"})
    assert (first.status_code, first.json()) == (again.status_code, again.json())
    assert len(_stored(engine)) == 1


def test_consent_is_required(client: TestClient, engine: Engine) -> None:
    response = client.post("/v1/waitlist", json={**BODY, "consent": False})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "consent_required"
    assert _stored(engine) == []


@pytest.mark.parametrize(
    "body",
    [
        {"email": "no-es-correo", "consent": True, "aviso_version": "2026-10"},
        {"email": "sintetico@example.test", "consent": True},
        {"email": "sintetico@example.test", "aviso_version": "2026-10"},
    ],
)
def test_invalid_requests(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/v1/waitlist", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "sintetico@example.test" not in response.text


def test_rate_limit_is_stable(client: TestClient) -> None:
    statuses = [
        client.post("/v1/waitlist", json={**BODY, "email": f"sintetico{i}@example.test"})
        for i in range(7)
    ]
    assert [r.status_code for r in statuses[:5]] == [202] * 5
    limited = statuses[5]
    assert limited.status_code == 429
    assert limited.json() == {
        "error": {"code": "rate_limited", "message": "Too many requests. Try again later."}
    }
    assert limited.headers["retry-after"] == "600"
    assert statuses[6].json() == limited.json()


def test_email_is_never_logged(client: TestClient, capfd: pytest.CaptureFixture[str]) -> None:
    client.post("/v1/waitlist", json=BODY)
    out, err = capfd.readouterr()
    assert "sintetico.uno" not in (out + err).lower()
