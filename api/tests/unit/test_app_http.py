"""App-level behaviour without a database: envelope, probes, headers, CORS and metrics."""

from __future__ import annotations

import socket
import urllib.request

import pytest
from fastapi.testclient import TestClient

from family_history.app import create_app
from family_history.metrics import start_metrics_server
from fh_testing import StubJWKClient, make_settings


@pytest.fixture
def client(jwk_client: StubJWKClient) -> TestClient:
    return TestClient(create_app(make_settings(), key_resolver=jwk_client))


def test_health_is_dependency_free(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_without_database_names_the_failing_part(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "db": "unconfigured", "migrations": "unknown"}


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/v1/nothing-here")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found."}}


def test_method_not_allowed_uses_envelope(client: TestClient) -> None:
    response = client.put("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_use_envelope_and_never_echo_input(jwk_client: StubJWKClient) -> None:
    settings = make_settings(FH_WAITLIST_ENABLED="true", FH_AVISO_VERSION="2026-10")
    client = TestClient(create_app(settings, key_resolver=jwk_client))
    secret = "correo.secreto@example.test"
    response = client.post("/v1/waitlist", json={"email": secret, "consent": "maybe"})
    assert response.status_code in (422, 503)
    if response.status_code == 422:
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert secret not in response.text


def test_closed_waitlist_answers_before_reading_input(client: TestClient) -> None:
    secret = "correo.secreto@example.test"
    response = client.post("/v1/waitlist", json={"email": secret, "consent": "maybe"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "waitlist_closed", "message": "The waitlist is not open."}
    }
    assert secret not in response.text


def test_malformed_json_is_a_validation_error(client: TestClient) -> None:
    response = client.post(
        "/v1/spaces",
        content=b"{not json",
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
    )
    assert response.status_code in (401, 422)
    assert "error" in response.json()


def test_unhandled_errors_become_internal_error(jwk_client: StubJWKClient) -> None:
    app = create_app(make_settings(), key_resolver=jwk_client)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("synthetic failure")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }


def test_request_id_is_generated_or_propagated(client: TestClient) -> None:
    generated = client.get("/health").headers["x-request-id"]
    assert len(generated) == 32
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"]
        == "abc-123"
    )
    spoofed = client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert spoofed.headers["x-request-id"] != "bad id\nwith newline"


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers


def test_hsts_outside_dev(jwk_client: StubJWKClient) -> None:
    app = create_app(
        make_settings(FH_ENV="production", FH_METRICS_PORT="0"), key_resolver=jwk_client
    )
    headers = TestClient(app).get("/health").headers
    assert headers["strict-transport-security"].startswith("max-age=")


def test_docs_are_off_outside_dev(jwk_client: StubJWKClient) -> None:
    app = create_app(make_settings(FH_ENV="staging", FH_METRICS_PORT="0"), key_resolver=jwk_client)
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cors_preflight_for_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/v1/spaces",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_unknown_origin(client: TestClient) -> None:
    response = client.options(
        "/v1/spaces",
        headers={"Origin": "https://evil.example.test", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_metrics_listener_is_separate_and_counts_requests(client: TestClient) -> None:
    client.get("/health")
    server = start_metrics_server(_free_port(), addr="127.0.0.1")
    try:
        url = f"http://127.0.0.1:{server.port}/metrics"
        body = urllib.request.urlopen(url, timeout=5).read().decode()  # noqa: S310
    finally:
        server.stop()
    assert "fh_http_request_duration_seconds_bucket" in body
    assert 'route="/health"' in body
    assert client.get("/metrics").status_code == 404


def test_lifespan_starts_and_stops_metrics(jwk_client: StubJWKClient) -> None:
    port = _free_port()
    app = create_app(make_settings(FH_METRICS_PORT=str(port)), key_resolver=jwk_client)
    with TestClient(app):
        body = urllib.request.urlopen(  # noqa: S310
            f"http://127.0.0.1:{port}/metrics", timeout=5
        ).read()
        assert b"fh_http_requests_total" in body
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=1)  # noqa: S310
