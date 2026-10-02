"""Event dates through the API, and the ranked people search (exact, variant, prefix)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from postgres.conftest import AuthHeaders

pytestmark = pytest.mark.postgres

ANA = "user-ana"


def _space(client: TestClient, auth: AuthHeaders) -> str:
    response = client.post("/v1/spaces", json={"name": "Familia"}, headers=auth(ANA))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _person(client: TestClient, auth: AuthHeaders, space: str, **name: Any) -> dict[str, Any]:
    response = client.post(
        f"/v1/spaces/{space}/people", json={"names": [name]}, headers=auth(ANA)
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _birth(space: str, person: dict[str, Any], **date: str) -> dict[str, Any]:
    return {
        "type": "birth",
        **date,
        "participants": [{"person_id": person["id"], "role": "principal"}],
    }


def test_event_dates_round_trip_through_the_api(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    person = _person(client, auth, space, given="Ana", apellido_paterno="Romero")
    typed = client.post(
        f"/v1/spaces/{space}/events",
        json=_birth(space, person, date_original="15 de marzo de 1923"),
        headers=auth(ANA),
    )
    assert typed.status_code == 201, typed.text
    event = typed.json()
    assert event["date_value"] == "15 MAR 1923"
    assert event["date_original"] == "15 de marzo de 1923"
    assert event["date_display"] == {"es": "15 de marzo de 1923", "en": "15 March 1923"}
    assert (event["date_earliest"], event["date_latest"]) == ("1923-03-15", "1923-03-15")

    canonical = client.patch(
        f"/v1/events/{event['id']}", json={"date_value": "bet 1890 and 1895"}, headers=auth(ANA)
    ).json()
    assert canonical["date_value"] == "BET 1890 AND 1895"
    assert canonical["date_original"] is None
    assert canonical["date_display"]["es"] == "entre 1890 y 1895"

    cleared = client.patch(
        f"/v1/events/{event['id']}", json={"date_value": None}, headers=auth(ANA)
    ).json()
    assert cleared["date_value"] is None and cleared["date_display"] is None
    assert cleared["date_earliest"] is None and cleared["date_latest"] is None

    detail = client.get(f"/v1/people/{person['id']}", headers=auth(ANA)).json()
    assert detail["living_status"] == "unknown"


@pytest.mark.parametrize(
    ("date", "code"),
    [
        ({"date_original": "1890-1895"}, "ambiguous_date"),
        ({"date_original": "el día del santo"}, "invalid_date"),
        ({"date_value": "hacia 1890"}, "invalid_date"),
        ({"date_value": "1890", "date_original": "1890"}, "validation_error"),
    ],
)
def test_bad_dates_are_rejected(
    client: TestClient, auth: AuthHeaders, date: dict[str, str], code: str
) -> None:
    space = _space(client, auth)
    person = _person(client, auth, space, given="Ana")
    response = client.post(
        f"/v1/spaces/{space}/events", json=_birth(space, person, **date), headers=auth(ANA)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_recent_birth_makes_a_person_living(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    young = _person(client, auth, space, given="Beto")
    old = _person(client, auth, space, given="Carla")
    for person, text in ((young, "2001"), (old, "hacia 1890")):
        response = client.post(
            f"/v1/spaces/{space}/events",
            json=_birth(space, person, date_original=text),
            headers=auth(ANA),
        )
        assert response.status_code == 201, response.text
    people = {
        item["display_name"]: item
        for item in client.get(f"/v1/spaces/{space}/people", headers=auth(ANA)).json()["items"]
    }
    assert people["Beto"]["living_status"] == "living"
    assert people["Beto"]["is_private"] is True
    assert people["Carla"]["living_status"] == "presumed_deceased"
    assert people["Carla"]["is_private"] is False


def test_search_ranks_exact_then_variant_then_prefix(
    client: TestClient, auth: AuthHeaders
) -> None:
    space = _space(client, auth)
    _person(client, auth, space, given="Jesús", apellido_paterno="Romero")
    _person(client, auth, space, given="Chucho", apellido_paterno="Zamora")
    _person(client, auth, space, given="Manuel", apellido_paterno="Zamora")
    _person(client, auth, space, given="Manolo", apellido_paterno="Benítez")
    _person(client, auth, space, given="Manuela", apellido_paterno="Álvarez")
    _person(client, auth, space, given="José María", apellido_paterno="Castro")
    _person(client, auth, space, given="Guadalupe", apellido_paterno="Hernández")

    def search(q: str) -> list[str]:
        response = client.get(f"/v1/spaces/{space}/people", params={"q": q}, headers=auth(ANA))
        assert response.status_code == 200, response.text
        return [item["display_name"] for item in response.json()["items"]]

    # Exact «Manuel», then the variant (Manolo), then the prefix (Manuela).
    assert search("Manuel") == ["Manuel Zamora", "Manolo Benítez", "Manuela Álvarez"]
    # Hipocorísticos work both ways: «Chucho» finds Jesús and «Jesús» finds Chucho.
    assert search("Chucho") == ["Chucho Zamora", "Jesús Romero"]
    assert search("jesus") == ["Jesús Romero", "Chucho Zamora"]
    # A multi-word variant needs every word: «Chema» is José María.
    assert search("Chema") == ["José María Castro"]
    assert search("Lupita") == ["Guadalupe Hernández"]
    # Spellings that sound alike fold together (z→s, h is silent).
    assert search("ernandes") == ["Guadalupe Hernández"]
    assert search("Romero Jesús") == ["Jesús Romero"]
    assert search("y") == search("")


def test_search_pages_keep_the_rank_order(client: TestClient, auth: AuthHeaders) -> None:
    space = _space(client, auth)
    for surname in ("Zamora", "Castro", "Benítez"):
        _person(client, auth, space, given="Manuel", apellido_paterno=surname)
    _person(client, auth, space, given="Manolo", apellido_paterno="Álvarez")
    _person(client, auth, space, given="Manuela", apellido_paterno="Durán")
    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"q": "manuel", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = client.get(f"/v1/spaces/{space}/people", params=params, headers=auth(ANA)).json()
        seen.extend(item["display_name"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [
        "Manuel Benítez",
        "Manuel Castro",
        "Manuel Zamora",
        "Manolo Álvarez",
        "Manuela Durán",
    ]
    plain_cursor = client.get(
        f"/v1/spaces/{space}/people", params={"limit": 1}, headers=auth(ANA)
    ).json()["next_cursor"]
    mixed = client.get(
        f"/v1/spaces/{space}/people",
        params={"q": "manuel", "cursor": plain_cursor},
        headers=auth(ANA),
    )
    assert mixed.status_code == 400
    assert mixed.json()["error"]["code"] == "invalid_cursor"
