"""Migrations and readiness against a real database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from family_history.db.migrate import downgrade_to_base, is_at_head, upgrade_to_head
from postgres.conftest import PgTarget

pytestmark = pytest.mark.postgres


def test_database_is_at_head(engine: Engine) -> None:
    with engine.connect() as conn:
        assert is_at_head(conn)


def test_ready_reports_db_and_migrations(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "db": "ok", "migrations": "head"}


def test_downgrade_and_upgrade_round_trip(
    migrated: PgTarget, engine: Engine, client: TestClient
) -> None:
    if migrated.created_database is None:
        pytest.skip("only on the throwaway database the suite created")
    downgrade_to_base(migrated.app_url)
    try:
        with engine.connect() as conn:
            assert not is_at_head(conn)
        behind = client.get("/ready")
        assert behind.status_code == 503
        assert behind.json()["migrations"] == "behind"
    finally:
        upgrade_to_head(migrated.app_url)
    with engine.connect() as conn:
        assert is_at_head(conn)
