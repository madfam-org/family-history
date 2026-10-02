"""Imports, exports and the worker against a real database, round trips included."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from family_history.cli import main as cli_main
from family_history.config import get_settings
from family_history.db.engine import Database
from family_history.gedcom.parse7 import parse_gedcom7
from family_history.worker.__main__ import healthcheck
from family_history.worker.runner import Worker, WorkerConfig
from postgres.conftest import AuthHeaders, PgTarget, add_member, scoped_execute

pytestmark = pytest.mark.postgres

ANA = "user-ana"
BETO = "user-beto"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "gedcom"


@pytest.fixture
def worker(database: Database, tmp_path: Path) -> Worker:
    return Worker(database, WorkerConfig(heartbeat_path=tmp_path / "heartbeat", poll_seconds=0))


@pytest.fixture
def seeded_env(migrated: PgTarget, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FH_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", migrated.app_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def drain(worker: Worker) -> int:
    ran = 0
    while worker.run_once():
        ran += 1
    return ran


def _space(client: TestClient, auth: AuthHeaders, name: str = "Familia") -> str:
    response = client.post("/v1/spaces", json={"name": name}, headers=auth(ANA))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _export(
    client: TestClient, auth: AuthHeaders, worker: Worker, space: str, fmt: str, sub: str = ANA
) -> tuple[dict[str, Any], bytes]:
    accepted = client.post(f"/v1/spaces/{space}/exports", json={"format": fmt}, headers=auth(sub))
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    drain(worker)
    job = client.get(f"/v1/jobs/{job_id}", headers=auth(sub)).json()
    assert job["status"] == "succeeded", job
    download = client.get(f"/v1/jobs/{job_id}/download", headers=auth(sub))
    assert download.status_code == 200, download.text
    assert download.headers["content-disposition"].startswith("attachment; filename=")
    return job, download.content


def _import(
    client: TestClient,
    auth: AuthHeaders,
    worker: Worker,
    space: str,
    filename: str,
    data: bytes,
    sub: str = ANA,
) -> dict[str, Any]:
    accepted = client.post(
        f"/v1/spaces/{space}/imports", files={"file": (filename, data)}, headers=auth(sub)
    )
    assert accepted.status_code == 202, accepted.text
    drain(worker)
    return dict(client.get(f"/v1/jobs/{accepted.json()['job_id']}", headers=auth(sub)).json())


def _seed(space: str, seed: int = 11, generations: int = 4) -> None:
    code = cli_main(
        ["seed-synth", "--space", space, "--seed", str(seed), "--generations", str(generations)]
    )
    assert code == 0


def test_native_round_trip_is_byte_identical(
    client: TestClient, auth: AuthHeaders, worker: Worker, seeded_env: None, tmp_path: Path
) -> None:
    first_space = _space(client, auth)
    _seed(first_space)
    job, first = _export(client, auth, worker, first_space, "native_json")
    assert job["report"]["counts"]["people"] > 20
    exported = tmp_path / "tree.json"
    exported.write_bytes(first)
    assert cli_main(["validate-export", str(exported)]) == 0

    second_space = _space(client, auth, "Copia")
    imported = _import(client, auth, worker, second_space, "tree.json", first)
    assert imported["status"] == "succeeded", imported
    assert imported["report"]["counts"] == job["report"]["counts"]
    _, second = _export(client, auth, worker, second_space, "native_json")
    assert second == first

    people = client.get(f"/v1/spaces/{second_space}/people", headers=auth(ANA)).json()["items"]
    statuses = {p["living_status"] for p in people}
    assert "living" in statuses and statuses - {"living", "unknown"}


def test_gedcom7_round_trip_is_byte_identical(
    client: TestClient, auth: AuthHeaders, worker: Worker, seeded_env: None
) -> None:
    first_space = _space(client, auth)
    _seed(first_space, seed=23)
    _, first = _export(client, auth, worker, first_space, "gedcom7")
    parse_gedcom7(first, strict=True)  # a valid GEDCOM 7.0 dataset
    second_space = _space(client, auth, "Copia")
    imported = _import(client, auth, worker, second_space, "familia.ged", first)
    assert imported["status"] == "succeeded", imported
    assert imported["report"]["source_version"] == "7.0"
    _, second = _export(client, auth, worker, second_space, "gedcom7")
    assert second == first

    _, archive = _export(client, auth, worker, first_space, "gedzip")
    assert archive.startswith(b"PK\x03\x04")
    from_zip = _import(client, auth, worker, _space(client, auth, "Zip"), "familia.gdz", archive)
    assert from_zip["status"] == "succeeded" and from_zip["report"]["format"] == "gedzip"

    legacy_job, legacy = _export(client, auth, worker, first_space, "gedcom551")
    assert b"2 VERS 5.5.1" in legacy
    reimported = _import(client, auth, worker, _space(client, auth, "Legado"), "l.ged", legacy)
    assert reimported["status"] == "succeeded", reimported
    assert reimported["report"]["counts"]["people"] == legacy_job["report"]["counts"]["people"]


@pytest.mark.parametrize(
    "fixture",
    [
        "ancestry-like-551.ged",
        "gramps-like-551-ansel.ged",
        "myheritage-like-551.ged",
        "rootsmagic-like-551.ged",
        "familia-sintetica-7.ged",
    ],
)
def test_vendor_files_import_with_a_report(
    client: TestClient, auth: AuthHeaders, worker: Worker, fixture: str
) -> None:
    space = _space(client, auth)
    job = _import(client, auth, worker, space, fixture, (FIXTURES / fixture).read_bytes())
    assert job["status"] == "succeeded", job
    report = job["report"]
    assert report["counts"]["people"] > 0
    assert report["source_version"]
    assert all(set(w) == {"code", "message", "line"} for w in report["warnings"])
    listed = client.get(f"/v1/spaces/{space}/people", headers=auth(ANA)).json()["items"]
    assert len(listed) == report["counts"]["people"]


def test_import_rules(
    client: TestClient, auth: AuthHeaders, worker: Worker, engine: Engine
) -> None:
    space = _space(client, auth)
    add_member(engine, uuid.UUID(space), BETO, "viewer")
    viewer = client.post(
        f"/v1/spaces/{space}/imports", files={"file": ("a.ged", b"0 HEAD")}, headers=auth(BETO)
    )
    assert viewer.status_code == 403 and viewer.json()["error"]["code"] == "insufficient_role"
    wrong = client.post(
        f"/v1/spaces/{space}/imports", files={"file": ("a.txt", b"hola")}, headers=auth(ANA)
    )
    assert wrong.status_code == 415 and wrong.json()["error"]["code"] == "unsupported_file_type"
    empty = client.post(
        f"/v1/spaces/{space}/imports", files={"file": ("a.ged", b"")}, headers=auth(ANA)
    )
    assert empty.json()["error"]["code"] == "empty_file"
    huge = client.post(
        f"/v1/spaces/{space}/imports",
        files={"file": ("a.ged", b"0" * (25 * 1024 * 1024 + 1))},
        headers=auth(ANA),
    )
    assert huge.status_code == 413 and huge.json()["error"]["code"] == "file_too_large"
    garbage = _import(client, auth, worker, space, "a.json", b'{"format": "otra cosa"}')
    assert garbage["status"] == "failed"
    assert garbage["error_code"] == "invalid_native_export"
    not_gedcom = _import(client, auth, worker, space, "a.ged", b"esto no es GEDCOM")
    assert not_gedcom["status"] == "failed" and not_gedcom["error_code"] == "not_gedcom"


def test_jobs_are_private_and_expire(
    client: TestClient, auth: AuthHeaders, worker: Worker, engine: Engine
) -> None:
    space = _space(client, auth)
    add_member(engine, uuid.UUID(space), BETO, "viewer")
    accepted = client.post(
        f"/v1/spaces/{space}/exports", json={"format": "gedcom7"}, headers=auth(ANA)
    ).json()
    job_id = accepted["job_id"]
    early = client.get(f"/v1/jobs/{job_id}/download", headers=auth(ANA))
    assert early.status_code == 409 and early.json()["error"]["code"] == "job_not_ready"
    drain(worker)
    other = client.get(f"/v1/jobs/{job_id}", headers=auth(BETO))
    assert other.status_code == 404 and other.json()["error"]["code"] == "job_not_found"
    # Any member may export, viewers included: the exit is free.
    viewer_export = client.post(
        f"/v1/spaces/{space}/exports", json={"format": "native_json"}, headers=auth(BETO)
    )
    assert viewer_export.status_code == 202
    # Request sessions cannot touch the queue: without `app.job_runner` updates match nothing.
    scoped_execute(
        engine,
        "UPDATE job SET status = 'queued'",
        user_sub=ANA,
        space_id=uuid.UUID(space),
    )
    assert client.get(f"/v1/jobs/{job_id}", headers=auth(ANA)).json()["status"] == "succeeded"
    _expire(engine, job_id)
    gone = client.get(f"/v1/jobs/{job_id}/download", headers=auth(ANA))
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "job_expired"
    assert worker.purge_expired() == 1


def _expire(engine: Engine, job_id: str) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("SELECT set_config('app.job_runner', 'on', true)")
        conn.exec_driver_sql(
            "UPDATE job SET expires_at = now() - interval '1 minute' WHERE id = %s", (job_id,)
        )


def test_export_holds_only_what_the_requester_sees(
    client: TestClient, auth: AuthHeaders, worker: Worker, engine: Engine
) -> None:
    space = _space(client, auth)
    add_member(engine, uuid.UUID(space), BETO, "editor")
    private = client.post(
        f"/v1/spaces/{space}/people",
        json={"visibility": "private", "names": [{"given": "Teresa", "apellido_paterno": "Luna"}]},
        headers=auth(ANA),
    ).json()
    shared = client.post(
        f"/v1/spaces/{space}/people",
        json={"names": [{"given": "Rafael", "apellido_paterno": "Luna"}]},
        headers=auth(ANA),
    ).json()
    client.post(
        f"/v1/spaces/{space}/events",
        json={
            "type": "baptism",
            "participants": [{"person_id": shared["id"], "role": "principal"}],
        },
        headers=auth(ANA),
    )
    _, mine = _export(client, auth, worker, space, "native_json")
    _, theirs = _export(client, auth, worker, space, "native_json", sub=BETO)
    assert b"Teresa" in mine and b"baptism" in mine
    assert b"Teresa" not in theirs and b"baptism" not in theirs
    assert b"Rafael" in theirs
    assert private["id"].encode() not in mine  # export-local ids only


def test_worker_reclaims_stuck_jobs_and_skips_locked_ones(
    client: TestClient, auth: AuthHeaders, worker: Worker, database: Database
) -> None:
    space = _space(client, auth)
    first = client.post(
        f"/v1/spaces/{space}/exports", json={"format": "gedcom7"}, headers=auth(ANA)
    ).json()["job_id"]
    second = client.post(
        f"/v1/spaces/{space}/exports", json={"format": "gedcom7"}, headers=auth(ANA)
    ).json()["job_id"]
    locker = database.sessions()
    try:
        locker.execute(
            text("SELECT set_config('app.job_runner', 'on', true)")
        )
        locker.execute(
            text("SELECT id FROM job WHERE id = :id FOR UPDATE"),
            {"id": first},
        )
        assert str(worker.claim()) == second  # the locked row is skipped
    finally:
        locker.rollback()
        locker.close()
    with database.engine.begin() as conn:
        conn.exec_driver_sql("SELECT set_config('app.job_runner', 'on', true)")
        conn.exec_driver_sql(
            "UPDATE job SET started_at = now() - interval '1 hour' WHERE id = %s", (second,)
        )
    assert [str(i) for i in worker.reclaim_stuck()] == [second]
    with database.engine.begin() as conn:
        conn.exec_driver_sql("SELECT set_config('app.job_runner', 'on', true)")
        conn.exec_driver_sql(
            "UPDATE job SET status = 'running', attempts = 3, "
            "started_at = now() - interval '1 hour' WHERE id = %s",
            (second,),
        )
    worker.reclaim_stuck()
    timed_out = client.get(f"/v1/jobs/{second}", headers=auth(ANA)).json()
    assert timed_out["status"] == "failed" and timed_out["error_code"] == "worker_timeout"
    # The loop itself: it runs the queued job, touches the heartbeat and stops on request.
    stop = threading.Event()
    loop = threading.Thread(target=worker.run_forever, args=(stop,))
    loop.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = client.get(f"/v1/jobs/{first}", headers=auth(ANA)).json()["status"]
            if state == "succeeded":
                break
            time.sleep(0.1)
    finally:
        stop.set()
        loop.join(timeout=10)
    assert not loop.is_alive()
    assert state == "succeeded"
    assert healthcheck(str(worker.config.heartbeat_path)) == 0
    assert healthcheck(str(worker.config.heartbeat_path), max_age=-1) == 1


def test_seed_synth_refuses_production(
    client: TestClient, auth: AuthHeaders, monkeypatch: pytest.MonkeyPatch
) -> None:
    space = _space(client, auth)
    monkeypatch.setenv("FH_ENV", "production")
    get_settings.cache_clear()
    try:
        assert cli_main(["seed-synth", "--space", space, "--seed", "1"]) == 2
    finally:
        get_settings.cache_clear()
