"""The JSON error envelope and the handlers that guarantee every error uses it.

Every error response is `{"error": {"code": "<snake_case>", "message": "<English>"}}`. Codes are
stable: the web app maps each one to Spanish copy. Messages never echo request input, so they
cannot leak names, emails or tokens.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("family_history.errors")


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class APIError(Exception):
    """An expected failure with a stable code. Raise it anywhere in request handling."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def not_found(code: str = "not_found", message: str = "Resource not found.") -> APIError:
    return APIError(404, code, message)


def forbidden(code: str = "forbidden", message: str = "Not allowed.") -> APIError:
    return APIError(403, code, message)


def conflict(code: str, message: str) -> APIError:
    return APIError(409, code, message)


def unprocessable(code: str, message: str) -> APIError:
    return APIError(422, code, message)


def envelope(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=envelope(code, message), headers=headers)


_HTTP_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def _describe_validation(exc: RequestValidationError) -> str:
    """Name the failing fields without echoing their values."""
    locations: list[str] = []
    for err in exc.errors()[:5]:
        loc = err.get("loc", ())
        parts = [str(part) for part in loc if part not in ("body", "query", "path", "header")]
        if parts:
            locations.append(".".join(parts))
    if not locations:
        return "The request is not valid."
    return "The request is not valid: " + ", ".join(sorted(set(locations))) + "."


async def _api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, APIError):
        raise exc
    return error_response(exc.status_code, exc.code, exc.message, exc.headers)


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return error_response(422, "validation_error", _describe_validation(exc))


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    status = exc.status_code
    code = _HTTP_CODES.get(status, "http_error")
    try:
        message = HTTPStatus(status).phrase + "."
    except ValueError:
        message = "HTTP error."
    return error_response(status, code, message, getattr(exc, "headers", None))


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled error", exc_info=(type(exc), exc, exc.__traceback__))
    return error_response(500, "internal_error", "An unexpected error occurred.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope, "description": HTTPStatus(status).phrase}
    for status in (400, 401, 403, 404, 409, 422, 429)
}
