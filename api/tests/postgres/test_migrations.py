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
    if not migrated.throwaway:
        pytest.skip("only on a throwaway database (created here, or CI's)")
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


def test_models_match_migrations(engine: Engine) -> None:
    """Autogenerate finds nothing to do: the migrations create exactly what the models say."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from family_history.models import Base

    # Mirrors env.py's include_object (importing env.py would run the migrations).
    optional = {"ix_person_search_trgm", "ix_place_search_trgm"}

    def keep(obj: object, name: str | None, type_: str, reflected: bool, other: object) -> bool:
        return not (type_ == "index" and reflected and name in optional)

    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_object": keep}
        )
        assert compare_metadata(context, Base.metadata) == []
