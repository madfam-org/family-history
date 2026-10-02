"""Postgres fixtures. Every test here is marked `postgres` and runs only when
`FH_TEST_DATABASE_URL` is set (the root conftest skips them otherwise).

When the URL's role can create roles and databases (a superuser, as in a throwaway container or
a CI service), the suite creates a fresh database owned by a new LOGIN role that is neither
superuser nor BYPASSRLS, migrates it as that role and connects the app as that role. Because the
migration FORCEs row-level security, the policies bind the table owner, so the tests exercise
RLS exactly as production does. Otherwise the URL's own role is used as-is, after checking that
it does not bypass RLS (CI's split: `FH_TEST_DATABASE_URL` is a NOSUPERUSER NOBYPASSRLS role
that owns the test database). When `FH_TEST_ADMIN_DATABASE_URL` is also set, that superuser
installs `pg_trgm` in the test database first. A database and role the suite created are dropped
at the end of the session.
"""

from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from family_history.app import create_app
from family_history.db.engine import Database, create_database, normalize_database_url
from family_history.db.migrate import upgrade_to_head
from fh_testing import StubJWKClient, TokenFactory, make_settings

APP_ROLE = "fh_rls_app"
TABLES = (
    "job",
    "event_participant",
    "association",
    "name_form",
    "relationship",
    "citation",
    "assertion",
    "event",
    "place",
    "source",
    "revision",
    "person",
    "space_member",
    "family_space",
    "waitlist_entry",
)


@dataclass
class PgTarget:
    app_url: str
    created_database: str | None

    @property
    def throwaway(self) -> bool:
        """Safe to downgrade: a database this suite created, or CI's (admin URL present)."""
        return self.created_database is not None or bool(
            os.environ.get("FH_TEST_ADMIN_DATABASE_URL")
        )


def _privileged(engine: Engine) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper OR (rolcreaterole AND rolcreatedb) "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).scalar()
    return bool(row)


def _install_extensions(database: str | None) -> None:
    """Optional: let the CI superuser install pg_trgm so the trigram indexes get created."""
    superuser_url = os.environ.get("FH_TEST_ADMIN_DATABASE_URL")
    if not superuser_url or not database:
        return
    url = make_url(normalize_database_url(superuser_url)).set(database=database)
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def pg_target() -> Iterator[PgTarget]:
    admin_url = normalize_database_url(os.environ["FH_TEST_DATABASE_URL"])
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    if not _privileged(admin):
        admin.dispose()
        _install_extensions(make_url(admin_url).database)
        yield PgTarget(app_url=admin_url, created_database=None)
        return
    password = secrets.token_hex(16)
    database = f"fh_api_test_{secrets.token_hex(4)}"
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE})
        verb = "ALTER" if exists.scalar() else "CREATE"
        # Hex-only throwaway password; DDL cannot take bind parameters.
        conn.execute(
            text(
                f"{verb} ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
                f"NOCREATEROLE PASSWORD '{password}'"
            )
        )
        conn.execute(text(f"CREATE DATABASE {database} OWNER {APP_ROLE}"))
    app_url = (
        make_url(admin_url)
        .set(username=APP_ROLE, password=password, database=database)
        .render_as_string(hide_password=False)
    )
    try:
        yield PgTarget(app_url=app_url, created_database=database)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {database} WITH (FORCE)"))
            conn.execute(text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
        admin.dispose()


@pytest.fixture(scope="session")
def migrated(pg_target: PgTarget) -> PgTarget:
    upgrade_to_head(pg_target.app_url)
    return pg_target


@pytest.fixture(scope="session")
def database(migrated: PgTarget) -> Iterator[Database]:
    db = create_database(migrated.app_url, pool_size=2, max_overflow=2)
    with db.engine.connect() as conn:
        bypass = conn.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    if bypass:
        pytest.fail("the app role bypasses RLS; point FH_TEST_DATABASE_URL at a non-superuser")
    yield db
    db.dispose()


@pytest.fixture
def engine(database: Database) -> Iterator[Engine]:
    """The app role's engine. Tables are emptied after each test (TRUNCATE ignores RLS)."""
    yield database.engine
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))


@pytest.fixture
def client(engine: Engine, database: Database, jwk_client: StubJWKClient) -> Iterator[TestClient]:
    app = create_app(make_settings(), database=database, key_resolver=jwk_client)
    with TestClient(app) as test_client:
        yield test_client


AuthHeaders = Callable[[str], dict[str, str]]


@pytest.fixture
def auth(make_token: TokenFactory) -> AuthHeaders:
    def headers(sub: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(sub)}"}

    return headers


def scoped_execute(
    engine: Engine,
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    user_sub: str | None = None,
    space_id: uuid.UUID | None = None,
) -> list[Any]:
    """Run raw SQL in one transaction with the given RLS settings; return the rows (if any)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "SELECT set_config('app.user_sub', :u, true), "
                "set_config('app.family_space_id', :s, true)"
            ),
            {"u": user_sub or "", "s": str(space_id) if space_id else ""},
        )
        result = conn.execute(text(sql), params or {})
        return list(result.all()) if result.returns_rows else []


def add_member(engine: Engine, space_id: uuid.UUID, user_sub: str, role: str) -> None:
    """Membership management has no endpoint yet (invites come with Janua org binding)."""
    scoped_execute(
        engine,
        "INSERT INTO space_member (id, family_space_id, user_sub, role, created_at, updated_at) "
        "VALUES (:id, :space, :sub, :role, now(), now())",
        {"id": uuid.uuid4(), "space": space_id, "sub": user_sub, "role": role},
        user_sub=user_sub,
        space_id=space_id,
    )
