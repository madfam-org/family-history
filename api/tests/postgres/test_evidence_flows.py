"""Sources, citations and append-only assertions."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from postgres.conftest import AuthHeaders, add_member

pytestmark = pytest.mark.postgres

ANA = "user-ana"


@pytest.fixture
def setup(client: TestClient, auth: AuthHeaders, engine: Engine) -> dict[str, Any]:
    space = client.post("/v1/spaces", json={"name": "Familia"}, headers=auth(ANA)).json()["id"]
    add_member(engine, uuid.UUID(space), "user-beto", "editor")
    add_member(engine, uuid.UUID(space), "user-carla", "contributor")
    person = client.post(
        f"/v1/spaces/{space}/people",
        json={"names": [{"given": "Ana", "apellido_paterno": "Romero"}]},
        headers=auth(ANA),
    ).json()
    source = client.post(
        f"/v1/spaces/{space}/sources",
        json={
            "type": "parish_book",
            "title": "Libro de bautismos sintético",
            "repository": "Parroquia Sintética",
            "locator": {"libro": "12"},
        },
        headers=auth(ANA),
    )
    assert source.status_code == 201, source.text
    citation = client.post(
        f"/v1/sources/{source.json()['id']}/citations",
        json={"foja": "34v", "partida": "112", "quality": 3, "extracted_text": "Texto sintético"},
        headers=auth(ANA),
    )
    assert citation.status_code == 201, citation.text
    return {
        "space": space,
        "person": person["id"],
        "source": source.json(),
        "citation": citation.json(),
    }


def _assert(client: TestClient, auth: AuthHeaders, space: str, sub: str, **body: Any) -> Any:
    return client.post(f"/v1/spaces/{space}/assertions", json=body, headers=auth(sub))


def test_sources_and_citations(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    assert setup["source"]["locator"] == {"libro": "12"}
    assert setup["citation"]["foja"] == "34v"
    listed = client.get(
        f"/v1/spaces/{setup['space']}/sources", params={"q": "bautismos"}, headers=auth(ANA)
    ).json()
    assert [s["id"] for s in listed] == [setup["source"]["id"]]
    citations = client.get(
        f"/v1/sources/{setup['source']['id']}/citations", headers=auth("user-beto")
    ).json()
    assert [c["id"] for c in citations] == [setup["citation"]["id"]]
    stranger = client.get(
        f"/v1/sources/{setup['source']['id']}/citations", headers=auth("user-dario")
    )
    assert stranger.json()["error"]["code"] == "source_not_found"


def test_assertion_lifecycle_is_append_only(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    space, person = setup["space"], setup["person"]
    suggested = _assert(
        client,
        auth,
        space,
        "user-carla",
        subject_type="person",
        subject_id=person,
        field="occupation",
        value={"text": "carpintero"},
    )
    assert suggested.status_code == 201, suggested.text
    first = suggested.json()
    assert first["status"] == "suggested" and first["citation_ids"] == []

    no_citation = client.post(
        f"/v1/assertions/{first['id']}/status", json={"status": "accepted"}, headers=auth(ANA)
    )
    assert no_citation.json()["error"]["code"] == "citation_required"

    linked = client.post(
        f"/v1/assertions/{first['id']}/citations",
        json={"citation_ids": [setup["citation"]["id"]]},
        headers=auth("user-carla"),
    ).json()
    assert linked["supersedes_id"] == first["id"]
    assert linked["citation_ids"] == [setup["citation"]["id"]]

    stale = client.post(
        f"/v1/assertions/{first['id']}/status", json={"status": "accepted"}, headers=auth(ANA)
    )
    assert stale.json()["error"]["code"] == "assertion_superseded"

    contributor = client.post(
        f"/v1/assertions/{linked['id']}/status",
        json={"status": "accepted"},
        headers=auth("user-carla"),
    )
    assert contributor.json()["error"]["code"] == "insufficient_role"

    accepted = client.post(
        f"/v1/assertions/{linked['id']}/status", json={"status": "accepted"}, headers=auth(ANA)
    ).json()
    assert accepted["status"] == "accepted"

    params = {"subject_type": "person", "subject_id": person}
    current = client.get(f"/v1/spaces/{space}/assertions", params=params, headers=auth(ANA)).json()
    assert [a["id"] for a in current] == [accepted["id"]]
    history = client.get(
        f"/v1/spaces/{space}/assertions",
        params={**params, "include_history": "true"},
        headers=auth(ANA),
    ).json()
    assert [a["status"] for a in history] == ["suggested", "suggested", "accepted"]

    detail = client.get(f"/v1/people/{person}", headers=auth(ANA)).json()
    assert [c["id"] for c in detail["citations"]] == [setup["citation"]["id"]]


def test_author_can_retract_own_assertion(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    created = _assert(
        client,
        auth,
        setup["space"],
        "user-carla",
        subject_type="person",
        subject_id=setup["person"],
        field="residence",
        value="Rancho Sintético",
    ).json()
    retracted = client.post(
        f"/v1/assertions/{created['id']}/status",
        json={"status": "retracted"},
        headers=auth("user-carla"),
    )
    assert retracted.status_code == 201
    assert retracted.json()["status"] == "retracted"


def test_accepting_on_create_needs_editor_and_citation(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    body = {
        "subject_type": "person",
        "subject_id": setup["person"],
        "field": "occupation",
        "value": "maestra",
        "status": "accepted",
    }
    assert (
        _assert(client, auth, setup["space"], "user-carla", **body).json()["error"]["code"]
        == "insufficient_role"
    )
    assert (
        _assert(client, auth, setup["space"], ANA, **body).json()["error"]["code"]
        == "citation_required"
    )
    ok = _assert(client, auth, setup["space"], ANA, **body, citation_ids=[setup["citation"]["id"]])
    assert ok.status_code == 201


def test_unknown_subject_and_citation(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    unknown_subject = _assert(
        client,
        auth,
        setup["space"],
        ANA,
        subject_type="event",
        subject_id=str(uuid.uuid4()),
        field="date",
        value="1900",
    )
    assert unknown_subject.json()["error"]["code"] == "unknown_subject"
    unknown_citation = _assert(
        client,
        auth,
        setup["space"],
        ANA,
        subject_type="person",
        subject_id=setup["person"],
        field="date",
        value="1900",
        citation_ids=[str(uuid.uuid4())],
    )
    assert unknown_citation.json()["error"]["code"] == "unknown_citation"


def test_sensitive_assertions_about_living_people_stay_with_author(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    created = _assert(
        client,
        auth,
        setup["space"],
        "user-carla",
        subject_type="person",
        subject_id=setup["person"],
        field="religion",
        value="sintética",
        sensitivity="religion",
    ).json()
    params = {"subject_type": "person", "subject_id": setup["person"]}
    author_view = client.get(
        f"/v1/spaces/{setup['space']}/assertions", params=params, headers=auth("user-carla")
    ).json()
    other_view = client.get(
        f"/v1/spaces/{setup['space']}/assertions", params=params, headers=auth(ANA)
    ).json()
    assert [a["id"] for a in author_view] == [created["id"]]
    assert other_view == []
    hidden = client.post(
        f"/v1/assertions/{created['id']}/status", json={"status": "disputed"}, headers=auth(ANA)
    )
    assert hidden.json()["error"]["code"] == "assertion_not_found"


def test_health_fields_default_to_health_sensitivity(
    client: TestClient, auth: AuthHeaders, setup: dict[str, Any]
) -> None:
    created = _assert(
        client,
        auth,
        setup["space"],
        "user-carla",
        subject_type="person",
        subject_id=setup["person"],
        field="cause_of_death",
        value="sintética",
    ).json()
    assert created["sensitivity"] == "health"
    params = {"subject_type": "person", "subject_id": setup["person"]}
    other_view = client.get(
        f"/v1/spaces/{setup['space']}/assertions", params=params, headers=auth(ANA)
    ).json()
    assert other_view == []
