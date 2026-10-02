"""M1 CRUD flows: spaces, people, search, pagination, relationships, events and roles."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from postgres.conftest import AuthHeaders, add_member, scoped_execute

pytestmark = pytest.mark.postgres

ANA = "user-ana"


def _space(client: TestClient, auth: AuthHeaders, sub: str = ANA, name: str = "Familia") -> str:
    response = client.post("/v1/spaces", json={"name": name}, headers=auth(sub))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _person(
    client: TestClient, auth: AuthHeaders, space: str, sub: str = ANA, **body: Any
) -> dict[str, Any]:
    payload = {"names": [{"given": "Ana", "apellido_paterno": "Romero"}], **body}
    response = client.post(f"/v1/spaces/{space}/people", json=payload, headers=auth(sub))
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_space_lifecycle(client: TestClient, auth: AuthHeaders) -> None:
    created = client.post("/v1/spaces", json={"name": "  Familia Sintética  "}, headers=auth(ANA))
    assert created.status_code == 201
    space = created.json()
    assert space["name"] == "Familia Sintética"
    assert space["role"] == "steward"
    assert space["people_count"] == 0
    listed = client.get("/v1/spaces", headers=auth(ANA)).json()
    assert [s["id"] for s in listed] == [space["id"]]
    renamed = client.patch(
        f"/v1/spaces/{space['id']}", json={"name": "Familia Renombrada"}, headers=auth(ANA)
    )
    assert renamed.json()["name"] == "Familia Renombrada"
    members = client.get(f"/v1/spaces/{space['id']}/members", headers=auth(ANA)).json()
    assert [(m["user_sub"], m["role"]) for m in members] == [(ANA, "steward")]
    me = client.get("/v1/me", headers=auth(ANA)).json()
    assert me["early_access"] is True
    assert me["spaces"][0]["name"] == "Familia Renombrada"


def test_other_users_cannot_see_a_space(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    person = _person(client, auth, space)
    for path in (f"/v1/spaces/{space}", f"/v1/spaces/{space}/people"):
        response = client.get(path, headers=auth("user-beto"))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "space_not_found"
    response = client.get(f"/v1/people/{person['id']}", headers=auth("user-beto"))
    assert response.json()["error"]["code"] == "person_not_found"
    assert client.get("/v1/spaces", headers=auth("user-beto")).json() == []


def test_person_create_get_patch_and_soft_delete(
    client: TestClient, auth: AuthHeaders, engine: Engine
) -> None:
    space = _space(client, auth)
    person = _person(
        client,
        auth,
        space,
        sex="F",
        names=[
            {
                "given": "María Guadalupe",
                "nombre_usado": "Lupita",
                "apellido_paterno": "Garza",
                "apellido_materno": "Treviño",
                "particles": {"paterno": "de la"},
                "nicknames": ["Lupe"],
            },
            {"given": "Guadalupe", "apellido_paterno": "Garza", "name_type": "religious"},
        ],
    )
    assert person["display_name"] == "María Guadalupe de la Garza Treviño"
    assert person["sort_name"] == "Garza Treviño, María Guadalupe de la"
    assert person["living_status"] == "unknown"
    assert person["is_private"] is True
    assert [n["is_primary"] for n in person["names"]] == [True, False]
    fetched = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    assert fetched == person

    patched = client.patch(
        f"/v1/people/{person['id']}",
        json={"names": [{"given": "Lupe", "apellido_paterno": "Garza", "is_primary": True}]},
        headers=auth(ANA),
    ).json()
    assert patched["display_name"] == "Lupe Garza"
    assert len(patched["names"]) == 1

    deleted = client.delete(f"/v1/people/{person['id']}", headers=auth(ANA))
    assert deleted.status_code == 204
    assert client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).status_code == 404
    assert client.get(f"/v1/spaces/{space}/people", headers=auth(ANA)).json()["items"] == []
    actions = scoped_execute(
        engine,
        "SELECT action FROM revision WHERE entity_id = :id ORDER BY created_at",
        {"id": uuid.UUID(person["id"])},
        user_sub=ANA,
        space_id=uuid.UUID(space),
    )
    assert [row.action for row in actions] == ["create", "update", "delete"]


def test_living_person_cannot_be_public(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    response = client.post(
        f"/v1/spaces/{space}/people",
        json={"names": [{"given": "Ana"}], "visibility": "public_memorial"},
        headers=auth(ANA),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "living_person_not_public"


def test_search_ignores_accents_and_case(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    _person(client, auth, space, names=[{"given": "José", "apellido_paterno": "Núñez"}])
    _person(client, auth, space, names=[{"given": "Juana", "apellido_paterno": "Pérez"}])
    _person(client, auth, space, names=[{"given": "Pedro", "nicknames": ["Perico"]}])

    def search(q: str) -> list[str]:
        response = client.get(f"/v1/spaces/{space}/people", params={"q": q}, headers=auth(ANA))
        return sorted(item["display_name"] for item in response.json()["items"])

    assert search("nunez") == ["José Núñez"]
    assert search("JOSE NÚÑEZ") == ["José Núñez"]
    assert search("pe") == ["Juana Pérez", "Pedro"]
    assert search("perico") == ["Pedro"]
    assert search("100%_") == []


def test_cursor_pagination(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    surnames = ["Zamora", "Álvarez", "Benítez", "Castro", "Durán"]
    for surname in surnames:
        _person(client, auth, space, names=[{"given": "Ana", "apellido_paterno": surname}])
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get(f"/v1/spaces/{space}/people", params=params, headers=auth(ANA)).json()
        seen.extend(item["display_name"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [
        "Ana Álvarez",
        "Ana Benítez",
        "Ana Castro",
        "Ana Durán",
        "Ana Zamora",
    ]
    bad = client.get(f"/v1/spaces/{space}/people", params={"cursor": "%%%"}, headers=auth(ANA))
    assert bad.json()["error"]["code"] == "invalid_cursor"


def test_relationships(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    parent = _person(client, auth, space)
    child = _person(client, auth, space, names=[{"given": "Beto"}])
    body = {
        "type": "parent_child",
        "from_person_id": parent["id"],
        "to_person_id": child["id"],
        "qualifier": "adopted",
    }
    created = client.post(f"/v1/spaces/{space}/relationships", json=body, headers=auth(ANA))
    assert created.status_code == 201
    rel = created.json()
    assert rel["qualifier"] == "adopted"
    duplicate = client.post(f"/v1/spaces/{space}/relationships", json=body, headers=auth(ANA))
    assert duplicate.json()["error"]["code"] == "relationship_exists"
    union = client.post(
        f"/v1/spaces/{space}/relationships",
        json={**body, "type": "union", "qualifier": "union_libre"},
        headers=auth(ANA),
    ).json()
    assert union["qualifier"] == "union_libre"
    detail = client.get(f"/v1/people/{child['id']}", headers=auth(ANA)).json()
    assert {r["id"] for r in detail["relationships"]} == {rel["id"], union["id"]}
    assert client.delete(f"/v1/relationships/{rel['id']}", headers=auth(ANA)).status_code == 204
    detail = client.get(f"/v1/people/{child['id']}", headers=auth(ANA)).json()
    assert [r["id"] for r in detail["relationships"]] == [union["id"]]


def test_cross_space_references_are_rejected(client: TestClient, auth: AuthHeaders) -> None:
    mine = _space(client, auth)
    theirs = _space(client, auth, sub="user-beto")
    stranger = _person(client, auth, theirs, sub="user-beto")
    own = _person(client, auth, mine)
    response = client.post(
        f"/v1/spaces/{mine}/relationships",
        json={
            "type": "union",
            "from_person_id": own["id"],
            "to_person_id": stranger["id"],
            "qualifier": "married",
        },
        headers=auth(ANA),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_person"


def test_events_update_living_status(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    person = _person(client, auth, space)
    place = client.post(
        f"/v1/spaces/{space}/places",
        json={"name": "San Miguel Sintético", "kind": "municipio", "inegi_code": "11003"},
        headers=auth(ANA),
    ).json()
    birth = client.post(
        f"/v1/spaces/{space}/events",
        json={
            "type": "birth",
            "date_value": "ABT 1920",
            "place_id": place["id"],
            "participants": [{"person_id": person["id"], "role": "principal"}],
        },
        headers=auth(ANA),
    )
    assert birth.status_code == 201, birth.text
    assert birth.json()["place"] == "San Miguel Sintético"
    death = client.post(
        f"/v1/spaces/{space}/events",
        json={"type": "death", "participants": [{"person_id": person["id"], "role": "principal"}]},
        headers=auth(ANA),
    ).json()
    # A death nobody has cited is not evidence: born about 1920, the person may be living.
    detail = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    assert detail["living_status"] == "living"
    assert detail["is_private"] is True
    assert len(detail["events"]) == 2

    source = client.post(
        f"/v1/spaces/{space}/sources",
        json={"type": "civil_registry_act", "title": "Registro Civil (sintético)"},
        headers=auth(ANA),
    ).json()
    citation = client.post(
        f"/v1/sources/{source['id']}/citations", json={"page": "Acta 12"}, headers=auth(ANA)
    ).json()
    cited = client.post(
        f"/v1/spaces/{space}/assertions",
        json={
            "subject_type": "event",
            "subject_id": death["id"],
            "field": "occurred",
            "value": True,
            "status": "accepted",
            "citation_ids": [citation["id"]],
        },
        headers=auth(ANA),
    )
    assert cited.status_code == 201, cited.text
    detail = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    assert detail["living_status"] == "deceased"
    assert detail["is_private"] is False
    listed = client.get(f"/v1/spaces/{space}/people", headers=auth(ANA)).json()["items"][0]
    assert listed["birth"] == {
        "date_value": "ABT 1920",
        "date_display": {"es": "hacia 1920", "en": "about 1920"},
        "place": "San Miguel Sintético",
    }
    assert listed["death"] == {"date_value": None, "date_display": None, "place": None}

    public = client.patch(
        f"/v1/people/{person['id']}", json={"visibility": "public_memorial"}, headers=auth(ANA)
    )
    assert public.json()["visibility"] == "public_memorial"
    updated = client.patch(
        f"/v1/events/{death['id']}", json={"date_original": "hacia 1990"}, headers=auth(ANA)
    ).json()
    assert updated["date_value"] == "ABT 1990"
    assert updated["date_original"] == "hacia 1990"
    assert updated["date_display"] == {"es": "hacia 1990", "en": "about 1990"}
    assert (updated["date_earliest"], updated["date_latest"]) == ("1985-01-01", "1995-12-31")
    # Retracting the only citation-bearing assertion takes the evidence away again.
    retracted = client.post(
        f"/v1/assertions/{cited.json()['id']}/status",
        json={"status": "retracted"},
        headers=auth(ANA),
    )
    assert retracted.status_code == 201, retracted.text
    detail = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    assert detail["living_status"] == "living"
    assert detail["visibility"] == "space"
    assert client.delete(f"/v1/events/{death['id']}", headers=auth(ANA)).status_code == 204


def test_sacraments_default_to_religion_and_stay_with_their_author(
    client: TestClient, auth: AuthHeaders, engine: Engine
) -> None:
    space = _space(client, auth)
    add_member(engine, uuid.UUID(space), "user-beto", "editor")
    person = _person(client, auth, space)
    baptism = client.post(
        f"/v1/spaces/{space}/events",
        json={
            "type": "baptism",
            "participants": [{"person_id": person["id"], "role": "principal"}],
        },
        headers=auth(ANA),
    ).json()
    assert baptism["sensitivity"] == "religion"
    mine = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    theirs = client.get(f"/v1/people/{person['id']}", headers=auth("user-beto")).json()
    assert [e["id"] for e in mine["events"]] == [baptism["id"]]
    assert theirs["events"] == []
    hidden = client.patch(
        f"/v1/events/{baptism['id']}", json={"description": "x"}, headers=auth("user-beto")
    )
    assert hidden.status_code == 404


def test_private_people_are_visible_only_to_their_creator(
    client: TestClient, auth: AuthHeaders, engine: Engine
) -> None:
    space = _space(client, auth)
    add_member(engine, uuid.UUID(space), "user-beto", "editor")
    private = _person(client, auth, space, visibility="private")
    shared = _person(client, auth, space, names=[{"given": "Beto"}])
    theirs = client.get(f"/v1/spaces/{space}/people", headers=auth("user-beto")).json()
    assert [p["id"] for p in theirs["items"]] == [shared["id"]]
    assert client.get(f"/v1/people/{private['id']}", headers=auth("user-beto")).status_code == 404
    summary = client.get(f"/v1/spaces/{space}", headers=auth("user-beto")).json()
    assert summary["people_count"] == 1


@pytest.mark.parametrize(
    ("role", "can_add", "can_edit", "can_rename"),
    [
        ("viewer", False, False, False),
        ("contributor", True, False, False),
        ("editor", True, True, False),
    ],
)
def test_role_gates(
    client: TestClient,
    auth: AuthHeaders,
    engine: Engine,
    role: str,
    can_add: bool,
    can_edit: bool,
    can_rename: bool,
) -> None:
    space = _space(client, auth)
    person = _person(client, auth, space)
    add_member(engine, uuid.UUID(space), "user-carla", role)
    carla = auth("user-carla")
    assert client.get(f"/v1/people/{person['id']}", headers=carla).status_code == 200
    add = client.post(
        f"/v1/spaces/{space}/people", json={"names": [{"given": "Nuevo"}]}, headers=carla
    )
    edit = client.patch(f"/v1/people/{person['id']}", json={"sex": "F"}, headers=carla)
    rename = client.patch(f"/v1/spaces/{space}", json={"name": "Otro"}, headers=carla)
    assert (add.status_code == 201) is can_add
    assert (edit.status_code == 200) is can_edit
    assert (rename.status_code == 200) is can_rename
    for response in (add, edit, rename):
        if response.status_code == 403:
            assert response.json()["error"]["code"] == "insufficient_role"
