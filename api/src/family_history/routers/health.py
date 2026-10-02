"""Liveness and readiness probes (docs/ARCHITECTURE.md §Runtime)."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from family_history.db.engine import Database
from family_history.db.migrate import is_at_head

logger = logging.getLogger("family_history.health")

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    db: Literal["ok", "unconfigured", "unreachable"]
    migrations: Literal["head", "behind", "unknown"]


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness: the process answers. No dependency checks."""
    return Health()


@router.get(
    "/ready",
    response_model=Readiness,
    responses={503: {"model": Readiness, "description": "A dependency is not ready"}},
)
def ready(request: Request) -> JSONResponse:
    """Readiness: the database answers and its schema is at the Alembic head."""
    database = getattr(request.app.state, "database", None)
    if not isinstance(database, Database):
        body = Readiness(status="not_ready", db="unconfigured", migrations="unknown")
        return JSONResponse(status_code=503, content=body.model_dump())
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            at_head = is_at_head(connection)
    except SQLAlchemyError as exc:
        logger.warning("readiness check failed", extra={"error_type": type(exc).__name__})
        body = Readiness(status="not_ready", db="unreachable", migrations="unknown")
        return JSONResponse(status_code=503, content=body.model_dump())
    if not at_head:
        body = Readiness(status="not_ready", db="ok", migrations="behind")
        return JSONResponse(status_code=503, content=body.model_dump())
    return JSONResponse(
        status_code=200, content=Readiness(status="ready", db="ok", migrations="head").model_dump()
    )
