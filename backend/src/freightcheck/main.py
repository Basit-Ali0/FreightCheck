# backend/src/freightcheck/main.py
"""FastAPI application entry point.

Wires the API router, the CORS middleware, structured logging, and the
exception handlers that map `FreightCheckError` subclasses to the API
Contract error shape `{"error": <class_name>, "detail": <message>}`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from freightcheck.api import audit as audit_router
from freightcheck.api import health as health_router
from freightcheck.api import sessions as sessions_router
from freightcheck.api import upload as upload_router
from freightcheck.errors import (
    DatabaseError,
    DuplicateAuditError,
    FileTooLargeError,
    FreightCheckError,
    ImageOnlyPDFError,
    InvalidFileTypeError,
    MissingDocumentError,
    PDFParseError,
    SessionNotFoundError,
)
from freightcheck.logging_config import configure_logging
from freightcheck.settings import settings

log = structlog.get_logger()

# HTTP status codes per API Contract §Response Status Codes.
_ERROR_STATUS: dict[type[FreightCheckError], int] = {
    MissingDocumentError: 400,
    InvalidFileTypeError: 400,
    DuplicateAuditError: 400,
    SessionNotFoundError: 404,
    FileTooLargeError: 413,
    ImageOnlyPDFError: 422,
    PDFParseError: 500,
    DatabaseError: 500,
}


def _error_response(exc: FreightCheckError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    configure_logging()

    app = FastAPI(title="FreightCheck API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.info(
            "api.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @app.exception_handler(FreightCheckError)
    async def _handle_freightcheck_error(
        _request: Request,
        exc: FreightCheckError,
    ) -> JSONResponse:
        status_code = _ERROR_STATUS.get(type(exc), 500)
        log.warning(
            "api.error",
            error_type=type(exc).__name__,
            detail=str(exc),
            status=status_code,
            context=exc.context,
        )
        return _error_response(exc, status_code)

    @app.get("/")
    async def _root() -> dict[str, str]:
        """Avoid a bare 404 when developers open the API host in a browser."""
        return {
            "service": "FreightCheck API",
            "health": "/health",
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    app.include_router(upload_router.router)
    app.include_router(audit_router.router)
    app.include_router(sessions_router.router)
    app.include_router(health_router.router)
    return app


app = create_app()
