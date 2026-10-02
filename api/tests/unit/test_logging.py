"""Logs never carry names, emails or tokens."""

from __future__ import annotations

import io
import json
import logging

from fastapi.testclient import TestClient

from family_history.app import create_app
from family_history.logging_setup import JsonFormatter, redact_value, scrub
from fh_testing import StubJWKClient, TokenFactory, make_settings


def _format(message: str, *args: object, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_scrub_removes_emails_bearer_tokens_and_jwts() -> None:
    text = (
        "user ana.lopez@example.test sent Authorization: Bearer abc.def-ghi "
        "and eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"
    )
    cleaned = scrub(text)
    assert "ana.lopez@example.test" not in cleaned
    assert "abc.def-ghi" not in cleaned
    assert "eyJhbGciOiJSUzI1NiJ9" not in cleaned


def test_sensitive_extra_keys_are_redacted() -> None:
    payload = _format(
        "created",
        email="ana@example.test",
        display_name="Ana López",
        given_name="Ana",
        access_token="tok",
        ip_hash="abc",
        status=201,
    )
    for key in ("email", "display_name", "given_name", "access_token", "ip_hash"):
        assert payload[key] == "[redacted]"
    assert payload["status"] == 201


def test_message_arguments_are_scrubbed() -> None:
    payload = _format("lookup for %s", "ana@example.test")
    assert payload["message"] == "lookup for [redacted]"


def test_nested_values_are_redacted() -> None:
    assert redact_value("details", {"email": "x@example.test", "count": 2}) == {
        "email": "[redacted]",
        "count": 2,
    }


def test_request_log_has_route_template_not_path_or_query(
    jwk_client: StubJWKClient, make_token: TokenFactory
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    client = TestClient(create_app(make_settings(), key_resolver=jwk_client))
    root.addHandler(handler)
    try:
        token = make_token("user-ana")
        client.get(
            "/v1/spaces/00000000-0000-0000-0000-000000000001/people",
            params={"q": "Guadalupe Hernández"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        root.removeHandler(handler)
    out = stream.getvalue()
    assert "Guadalupe" not in out
    assert token not in out
    assert "user-ana@example.test" not in out
    request_lines = [json.loads(line) for line in out.splitlines() if '"request"' in line]
    assert request_lines
    assert request_lines[-1]["route"] == "/v1/spaces/{space_id}/people"
    assert request_lines[-1]["status"] == 503
