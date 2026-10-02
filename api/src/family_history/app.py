"""The FastAPI application: `uvicorn family_history.app:app --host 0.0.0.0 --port 8000`."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import family_history
from family_history.auth import SigningKeyResolver, TokenVerifier
from family_history.config import Settings, get_settings
from family_history.db.engine import Database, create_database
from family_history.errors import install_error_handlers
from family_history.logging_setup import configure_logging, request_id_var
from family_history.metrics import MetricsServer, observe_request, start_metrics_server
from family_history.routers import (
    assertions,
    associations,
    events,
    health,
    jobs,
    kinship,
    people,
    places,
    relationships,
    sources,
    spaces,
    waitlist,
)
from family_history.services.ratelimit import AddressHasher, SlidingWindowLimiter

logger = logging.getLogger("family_history.app")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
HSTS = "max-age=63072000; includeSubDomains"


class RequestContextMiddleware:
    """Request id, security headers, request metrics and one redacted log line per request.

    The log line carries the route template (`/v1/people/{person_id}`), never the raw path or
    query string, so search terms and ids of people never reach the logs.
    """

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        path: str = scope.get("path", "")
        status_code = 500
        started = time.perf_counter()

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in BASE_SECURITY_HEADERS.items():
                    if name not in headers:
                        headers[name] = value
                if not path.startswith(_DOCS_PREFIXES) and "content-security-policy" not in headers:
                    headers["Content-Security-Policy"] = API_CSP
                if self.hsts:
                    headers["Strict-Transport-Security"] = HSTS
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            elapsed = time.perf_counter() - started
            route = scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            method = str(scope.get("method", ""))
            observe_request(method, template, status_code, elapsed)
            logger.info(
                "request",
                extra={
                    "method": method,
                    "route": template,
                    "status": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            request_id_var.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    metrics_server: MetricsServer | None = None
    if settings.metrics_port is not None:
        metrics_server = start_metrics_server(settings.metrics_port)
    logger.info(
        "api started",
        extra={"env": settings.env.value, "database": app.state.database is not None},
    )
    try:
        yield
    finally:
        if metrics_server is not None:
            metrics_server.stop()
        database = app.state.database
        if isinstance(database, Database):
            database.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    key_resolver: SigningKeyResolver | None = None,
) -> FastAPI:
    """Build the application. Tests inject settings, a database and a JWKS stub."""
    settings = settings or get_settings()
    configure_logging()
    dev = settings.is_dev
    app = FastAPI(
        title="family-history API",
        version=family_history.__version__,
        summary="Evidence-based family trees and family memory. AGPL-3.0-only.",
        lifespan=lifespan,
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.state.settings = settings
    if database is None and settings.database_url is not None:
        database = create_database(settings.database_url.get_secret_value())
    app.state.database = database
    app.state.token_verifier = TokenVerifier(settings, key_resolver=key_resolver)
    app.state.waitlist_limiter = SlidingWindowLimiter(
        settings.waitlist_rate_limit, settings.waitlist_rate_window_seconds
    )
    app.state.address_hasher = AddressHasher()

    install_error_handlers(app)
    for module in (
        health,
        spaces,
        people,
        relationships,
        events,
        places,
        sources,
        assertions,
        associations,
        kinship,
        jobs,
        waitlist,
    ):
        app.include_router(module.router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, hsts=not dev)
    return app


def openapi_document(app: FastAPI | None = None) -> dict[str, Any]:
    """The OpenAPI document, independent of whether the docs routes are mounted."""
    target = app or create_app(Settings.model_validate({"FH_ENV": "test"}))
    return target.openapi()


app = create_app()
