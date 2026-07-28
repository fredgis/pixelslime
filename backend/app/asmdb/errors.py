"""Typed failures raised by the asmDB REST client."""

from __future__ import annotations


class AsmDbError(RuntimeError):
    """Carry service context without exposing request headers or credentials."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        detail: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


class AsmDbNotFound(AsmDbError):  # noqa: N818
    """Signal that a requested row or card does not exist."""


class AsmDbUnauthorized(AsmDbError):  # noqa: N818
    """Signal a missing or invalid instance bearer credential."""


class AsmDbValidationError(AsmDbError):
    """Signal invalid local input or a server-side validation rejection."""


class AsmDbStarting(AsmDbError):  # noqa: N818
    """Signal that a scale-to-zero instance is still becoming ready."""


class AsmDbRateLimited(AsmDbError):  # noqa: N818
    """Signal throttling while retaining the server's retry delay."""
