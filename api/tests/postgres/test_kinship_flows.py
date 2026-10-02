"""Kinship, compadrazgo and associations through the API."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from postgres.conftest import AuthHeaders, add_member

pytestmark = pytest.mark.postgres

ANA = "user-ana"
BETO = "user-beto"


def _post(client: TestClient, auth: AuthHeaders, path: str, body: dict[str, Any]) -> Any:
    response = client.post(path, json=body, headers=auth(ANA))
    assert response.status_code in (201, 202), response.text
    return response.json()


def _family(client: TestClient, auth: AuthHeaders) -> dict[str, str]:
    space = _post(client, auth, "/v1/spaces", {"name": "Familia"})["id"]
    people: dict[str, str] = {"space": space}
    for key, given, sex in (
        ("abuelo", "Manuel", "M"),
        ("abuela", "Teresa", "F"),
        ("padre", "Rafael", "M"),
        ("madre", "Isabel", "F"),
        ("nieta", "Guadalupe", "F"),
        ("padrino", "Jesús", "M"),
        ("ajeno", "Ana", "F"),
    ):
        body = {"sex": sex, "names": [{"given": given, "apellido_paterno": "Romero"}]}
        people[key] = _post(client, auth, f"/v1/spaces/{space}/people", body)["id"]
    edges = (
        ("union", "abuelo", "abuela", "married"),
        ("parent_child", "abuelo", "padre", "birth"),
        ("parent_child", "abuela", "padre", "birth"),
        ("union", "padre", "madre", "union_libre"),
        ("parent_child", "padre", "nieta", "birth"),
        ("parent_child", "madre", "nieta", "birth"),
    )
    for kind, a, b, qualifier in edges:
        _post(
            client,
            auth,
            f"/v1/spaces/{space}/relationships",
            {
                "type": kind,
                "from_person_id": people[a],
                "to_person_id": people[b],
                "qualifier": qualifier,
            },
        )
    baptism = _post(
        client,
        auth,
        f"/v1/spaces/{space}/events",
        {
            "type": "baptism",
            "date_original": "2015",
            "participants": [{"person_id": people["nieta"], "role": "principal"}],
        },
    )
    people["baptism"] = baptism["id"]
    return people


def test_kinship_labels_and_structure(client: TestClient, auth: AuthHeaders) -> None:
    f = _family(client, auth)
    response = client.get(
        f"/v1/people/{f['nieta']}/kinship", params={"to": f["abuelo"]}, headers=auth(ANA)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label_es"] == "abuelo"
    assert body["label_en"] == "grandfather"
    assert body["kinship"]["kind"] == "blood"
    assert (body["kinship"]["up"], body["kinship"]["down"]) == (2, 0)

    in_law = client.get(
        f"/v1/people/{f['madre']}/kinship", params={"to": f["abuela"]}, headers=auth(ANA)
    ).json()
    assert in_law["label_es"] == "suegra"
    assert in_law["kinship"]["kind"] == "in_law"

    unrelated = client.get(
        f"/v1/people/{f['nieta']}/kinship", params={"to": f["ajeno"]}, headers=auth(ANA)
    )
    assert unrelated.status_code == 404
    assert unrelated.json()["error"]["code"] == "no_relation"
    missing = client.get(
        f"/v1/people/{f['nieta']}/kinship", params={"to": str(uuid.uuid4())}, headers=auth(ANA)
    )
    assert missing.json()["error"]["code"] == "person_not_found"


def test_kinship_stays_inside_one_space(client: TestClient, auth: AuthHeaders) -> None:
    f = _family(client, auth)
    other = _post(client, auth, "/v1/spaces", {"name": "Otra familia"})["id"]
    stranger = _post(
        client, auth, f"/v1/spaces/{other}/people", {"names": [{"given": "Ana"}]}
    )["id"]
    response = client.get(
        f"/v1/people/{f['nieta']}/kinship", params={"to": stranger}, headers=auth(ANA)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "person_not_found"


def test_associations_and_compadrazgo(
    client: TestClient, auth: AuthHeaders, engine: Engine
) -> None:
    f = _family(client, auth)
    space = f["space"]
    association = _post(
        client,
        auth,
        f"/v1/spaces/{space}/associations",
        {"event_id": f["baptism"], "person_id": f["padrino"], "role": "godparent"},
    )
    assert association["role"] == "godparent" and association["phrase"] is None

    repeat = client.post(
        f"/v1/spaces/{space}/associations",
        json={"event_id": f["baptism"], "person_id": f["padrino"], "role": "godparent"},
        headers=auth(ANA),
    )
    assert repeat.status_code == 409
    assert repeat.json()["error"]["code"] == "association_exists"
    own = client.post(
        f"/v1/spaces/{space}/associations",
        json={"event_id": f["baptism"], "person_id": f["nieta"], "role": "witness"},
        headers=auth(ANA),
    )
    assert own.json()["error"]["code"] == "association_is_principal"
    no_phrase = client.post(
        f"/v1/spaces/{space}/associations",
        json={"event_id": f["baptism"], "person_id": f["abuela"], "role": "other"},
        headers=auth(ANA),
    )
    assert no_phrase.json()["error"]["code"] == "validation_error"
    unknown = client.post(
        f"/v1/spaces/{space}/associations",
        json={"event_id": str(uuid.uuid4()), "person_id": f["abuela"], "role": "witness"},
        headers=auth(ANA),
    )
    assert unknown.json()["error"]["code"] == "unknown_event"

    detail = client.get(f"/v1/people/{f['nieta']}", headers=auth(ANA)).json()
    assert detail["events"][0]["associations"] == [
        {"id": association["id"], "person_id": f["padrino"], "role": "godparent", "phrase": None}
    ]

    of_padrino = client.get(f"/v1/people/{f['padrino']}/compadrazgo", headers=auth(ANA)).json()
    labels = {(i["display_name"], i["relation"], i["label_es"]) for i in of_padrino["items"]}
    assert labels == {
        ("Guadalupe Romero", "godchild", "ahijada de bautizo"),
        ("Rafael Romero", "compadre", "compadre de bautizo"),
        ("Isabel Romero", "compadre", "comadre de bautizo"),
    }
    assert {i["sacrament"] for i in of_padrino["items"]} == {"bautizo"}
    of_mother = client.get(f"/v1/people/{f['madre']}/compadrazgo", headers=auth(ANA)).json()
    assert [(i["person_id"], i["label_en"]) for i in of_mother["items"]] == [
        (f["padrino"], "compadre (baptism)")
    ]

    # The baptism of a living child is religion-sensitive and was recorded by Ana: another
    # member sees neither the event nor the compadrazgo it creates.
    add_member(engine, uuid.UUID(space), BETO, "editor")
    hidden = client.get(f"/v1/people/{f['madre']}/compadrazgo", headers=auth(BETO)).json()
    assert hidden == {"items": []}

    gone = client.delete(f"/v1/associations/{association['id']}", headers=auth(ANA))
    assert gone.status_code == 204
    after = client.get(f"/v1/people/{f['padrino']}/compadrazgo", headers=auth(ANA)).json()
    assert after == {"items": []}
    missing = client.delete(f"/v1/associations/{association['id']}", headers=auth(ANA))
    assert missing.json()["error"]["code"] == "association_not_found"
