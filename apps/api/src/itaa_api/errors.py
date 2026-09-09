"""Closed HTTP error mapping. Never echo submitted values or exception text."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from itaa_application.errors import ApplicationError
from itaa_application.golden_path import http_status_for, map_closed_error
from itaa_domain.errors import DomainInvariantError
from itaa_domain.identifiers import CorrelationId

_FALLBACK_CORRELATION = "cr_01k2m3n4p5q6r7s8t9v0w1x2zz"


def correlation_from(request: Request) -> str:
    raw = request.headers.get("x-correlation-id")
    if raw is None:
        return _FALLBACK_CORRELATION
    try:
        return CorrelationId(raw).to_primitive()
    except DomainInvariantError:
        return _FALLBACK_CORRELATION


def closed_body(error: ApplicationError, correlation_id: str) -> dict[str, object]:
    return {
        "error": {
            "code": error.code,
            "field": error.field,
            "correlationId": correlation_id,
        }
    }


async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=http_status_for(exc),
        content=closed_body(exc, correlation_from(request)),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del exc
    error = ApplicationError("payload", "schema_invalid")
    return JSONResponse(status_code=400, content=closed_body(error, correlation_from(request)))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "unknown_resource" if exc.status_code == 404 else "malformed"
    field = "path" if exc.status_code == 404 else "request"
    error = ApplicationError(field, code)
    status = 404 if exc.status_code == 404 else exc.status_code
    if status not in {400, 404, 409, 422, 500}:
        status = 400
    return JSONResponse(status_code=status, content=closed_body(error, correlation_from(request)))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = map_closed_error(exc)
    return JSONResponse(status_code=500, content=closed_body(error, correlation_from(request)))
