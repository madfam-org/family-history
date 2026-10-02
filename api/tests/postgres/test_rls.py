"""Row-level security: the database itself keeps family spaces apart."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from postgres.conftest import AuthHeaders, add_member, scoped_execute

pytestmark = pytest.mark.postgres

PERSON = {"names": [{"given": "Ana", "apellido_paterno": "Romero"}]}


def _space_with_person(client: TestClient, auth: AuthHeaders, sub: str) -> tuple[str, str]:
    space = client.post("/v1/spaces", json={"name": f"Familia de {sub}"}, headers=auth(sub))
    assert space.status_code == 201, space.text
    space_id = space.json()["id"]
    person = client.post(f"/v1/spaces/{space_id}/people", json=PERSON, headers=auth(sub))
    assert person.status_code == 201, person.text
    return space_id, person.json()["id"]


@pytest.fixture
def two_spaces(client: TestClient, auth: AuthHeaders) -> dict[str, Any]:
    space_a, person_a = _space_with_person(client, auth, "user-ana")
    space_b, person_b = _space_with_person(client, auth, "user-beto")
    return {
        "a": uuid.UUID(space_a),
        "b": uuid.UUID(space_b),
        "person_a": uuid.UUID(person_a),
        "person_b": uuid.UUID(person_b),
    }


def test_app_role_is_not_privileged(engine: Engine) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
    assert tuple(row) == (False, False)


def test_rls_is_enabled_and_forced_everywhere(engine: Engine) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
                "AND relname <> 'alembic_version'"
            )
        ).all()
    assert len(rows) == 14
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)


def test_raw_select_without_scope_sees_nothing(engine: Engine, two_spaces: dict[str, Any]) -> None:
    for table in ("person", "name_form", "revision", "family_space", "space_member"):
        assert scoped_execute(engine, f"SELECT * FROM {table}") == []  # noqa: S608


def test_raw_select_of_another_space_returns_nothing(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    # Ana scoped to her own space cannot see Beto's rows, even when asking for them by id.
    rows = scoped_execute(
        engine,
        "SELECT id FROM person WHERE id = :id",
        {"id": two_spaces["person_b"]},
        user_sub="user-ana",
        space_id=two_spaces["a"],
    )
    assert rows == []
    # Nor by pointing the space setting at Beto's space: she is not a member there.
    rows = scoped_execute(
        engine, "SELECT id FROM person", user_sub="user-ana", space_id=two_spaces["b"]
    )
    assert rows == []
    # Her own rows are visible.
    rows = scoped_execute(
        engine, "SELECT id FROM person", user_sub="user-ana", space_id=two_spaces["a"]
    )
    assert [row.id for row in rows] == [two_spaces["person_a"]]


def test_user_scope_alone_sees_only_member_spaces(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    people = scoped_execute(engine, "SELECT id FROM person", user_sub="user-ana")
    assert [row.id for row in people] == [two_spaces["person_a"]]
    spaces = scoped_execute(engine, "SELECT id FROM family_space", user_sub="user-ana")
    assert [row.id for row in spaces] == [two_spaces["a"]]
    members = scoped_execute(engine, "SELECT user_sub FROM space_member", user_sub="user-ana")
    assert [row.user_sub for row in members] == ["user-ana"]


def _insert_person(engine: Engine, space: uuid.UUID, **scope: Any) -> None:
    scoped_execute(
        engine,
        "INSERT INTO person (id, family_space_id, sex, living_status, visibility, search_text, "
        "sort_name, created_by, created_at, updated_at) VALUES (:id, :space, 'U', 'living', "
        "'space', '', '', 'user-ana', now(), now())",
        {"id": uuid.uuid4(), "space": space},
        **scope,
    )


def test_write_into_another_space_fails(engine: Engine, two_spaces: dict[str, Any]) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        _insert_person(engine, two_spaces["b"], user_sub="user-ana", space_id=two_spaces["a"])
    with pytest.raises(DBAPIError, match="row-level security"):
        _insert_person(engine, two_spaces["b"], user_sub="user-ana", space_id=two_spaces["b"])
    with pytest.raises(DBAPIError, match="row-level security"):
        _insert_person(engine, two_spaces["a"], user_sub="user-ana")


def test_update_and_delete_of_another_space_touch_nothing(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    scope = {"user_sub": "user-ana", "space_id": two_spaces["a"]}
    scoped_execute(
        engine,
        "UPDATE person SET sex = 'F' WHERE id = :id",
        {"id": two_spaces["person_b"]},
        **scope,
    )
    scoped_execute(
        engine, "DELETE FROM person WHERE id = :id", {"id": two_spaces["person_b"]}, **scope
    )
    rows = scoped_execute(
        engine,
        "SELECT sex FROM person WHERE id = :id",
        {"id": two_spaces["person_b"]},
        user_sub="user-beto",
        space_id=two_spaces["b"],
    )
    assert [row.sex for row in rows] == ["U"]


def test_viewers_cannot_write_at_the_database_level(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    add_member(engine, two_spaces["a"], "user-carla", "viewer")
    readable = scoped_execute(
        engine, "SELECT id FROM person", user_sub="user-carla", space_id=two_spaces["a"]
    )
    assert len(readable) == 1
    with pytest.raises(DBAPIError, match="row-level security"):
        _insert_person(engine, two_spaces["a"], user_sub="user-carla", space_id=two_spaces["a"])


def test_assertions_and_revisions_are_append_only(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    scope = {"user_sub": "user-ana", "space_id": two_spaces["a"]}
    revisions = scoped_execute(engine, "SELECT id FROM revision", **scope)
    assert revisions
    scoped_execute(engine, "UPDATE revision SET action = 'tampered'", **scope)
    scoped_execute(engine, "DELETE FROM revision", **scope)
    after = scoped_execute(engine, "SELECT action FROM revision", **scope)
    assert len(after) == len(revisions)
    assert "tampered" not in {row.action for row in after}


def test_family_space_cannot_be_renamed_by_non_steward(
    engine: Engine, two_spaces: dict[str, Any]
) -> None:
    add_member(engine, two_spaces["a"], "user-dario", "editor")
    scoped_execute(
        engine,
        "UPDATE family_space SET name = 'Otro nombre'",
        user_sub="user-dario",
        space_id=two_spaces["a"],
    )
    rows = scoped_execute(
        engine, "SELECT name FROM family_space", user_sub="user-ana", space_id=two_spaces["a"]
    )
    assert [row.name for row in rows] == ["Familia de user-ana"]


def test_waitlist_is_insert_only_for_the_api(engine: Engine) -> None:
    scoped_execute(
        engine,
        "INSERT INTO waitlist_entry (id, email, locale, consent_at, aviso_version, created_at) "
        "VALUES (:id, 'sintetico@example.test', 'es-MX', now(), 'v1', now())",
        {"id": uuid.uuid4()},
    )
    assert scoped_execute(engine, "SELECT email FROM waitlist_entry") == []
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.waitlist_relay', 'on', true)"))
        relayed = conn.execute(text("SELECT email FROM waitlist_entry")).all()
    assert [row.email for row in relayed] == ["sintetico@example.test"]
