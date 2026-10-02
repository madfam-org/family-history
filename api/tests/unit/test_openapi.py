"""The committed OpenAPI contract matches the code."""

from __future__ import annotations

import json
from pathlib import Path

from family_history.cli import current_openapi, default_contract_path, main

CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"


def test_contract_has_not_drifted() -> None:
    assert CONTRACT.read_text(encoding="utf-8") == current_openapi(), (
        "run `python -m family_history.cli openapi`"
    )


def test_rendering_is_deterministic() -> None:
    assert current_openapi() == current_openapi()


def test_contract_covers_the_v1_surface() -> None:
    paths = json.loads(current_openapi())["paths"]
    expected = {
        ("get", "/v1/me"),
        ("get", "/v1/spaces"),
        ("post", "/v1/spaces"),
        ("get", "/v1/spaces/{space_id}/people"),
        ("post", "/v1/spaces/{space_id}/people"),
        ("get", "/v1/people/{person_id}"),
        ("patch", "/v1/people/{person_id}"),
        ("post", "/v1/spaces/{space_id}/relationships"),
        ("post", "/v1/waitlist"),
        ("get", "/health"),
        ("get", "/ready"),
    }
    present = {(method, path) for path, ops in paths.items() for method in ops}
    assert expected <= present


def test_check_openapi_detects_drift(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text("{}\n", encoding="utf-8")
    assert main(["check-openapi", "--path", str(stale)]) == 1
    assert main(["openapi", "--output", str(stale)]) == 0
    assert main(["check-openapi", "--path", str(stale)]) == 0
    assert main(["check-openapi", "--path", str(tmp_path / "missing.json")]) == 1


def test_default_contract_path_finds_the_repository() -> None:
    assert default_contract_path() == CONTRACT


def test_migrate_needs_direct_database_url() -> None:
    assert main(["migrate"]) == 2
