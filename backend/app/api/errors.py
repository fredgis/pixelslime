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


def _is_serial_path_error(err: dict[str, Any]) -> bool:
    """True when a validation error is about the ``{serial}`` path parameter."""
    loc = err.get("loc", ())
    return len(loc) >= 2 and loc[0] == "path" and loc[1] == "serial"


def install_error_handlers(app: FastAPI) -> None:
    """Register the handlers that render errors as the contract envelope."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        if any(_is_serial_path_error(err) for err in errors):
            # A non-numeric or out-of-range serial is, to a visitor, just a card that
            # does not exist. Return the contract's clean 404 (matching W6's mock)
            # instead of FastAPI's 422, which would leak a path-validation internal
            # for e.g. /api/cards/abc or /api/cards/99999 (W10's V4).
            return JSONResponse(
                status_code=404,
                content=error_body("card_not_found", "No card with that serial"),
            )
        first = errors[0] if errors else {"msg": "invalid request"}
        location = ".".join(str(part) for part in first.get("loc", ()) if part != "query")
        message = first.get("msg", "invalid request")
        detail = f"{location}: {message}" if location else message
        return JSONResponse(status_code=422, content=error_body("invalid_request", detail))
