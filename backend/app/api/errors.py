"""The single error envelope every JSON error uses.

``contracts/openapi.yaml`` defines exactly one error shape —
``{"error": {"code", "message"}}`` — so this module gives the routes one exception
to raise (:class:`ApiError`) and wires the handlers that render it, including the
one that reshapes FastAPI's default 422 body into the same envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

_log = get_logger(__name__)


class ApiError(Exception):
    """An error that renders as the contract's ``Error`` envelope."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, Any]:
    """Build the ``{"error": {...}}`` document."""
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    """Register the handlers that render errors as the contract envelope."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"msg": "invalid request"}
        location = ".".join(str(part) for part in first.get("loc", ()) if part != "query")
        message = first.get("msg", "invalid request")
        detail = f"{location}: {message}" if location else message
        return JSONResponse(status_code=422, content=error_body("invalid_request", detail))
