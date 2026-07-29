"""Failures raised by job orchestration rather than its external dependencies."""

from __future__ import annotations


class JobError(RuntimeError):
    """Base class for a bloom that could not be safely published."""


class GenerationJobError(JobError):
    """Carry the pipeline stage and retryability into logs and operators."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        retryable: bool,
        retries_consumed: int,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retries_consumed = retries_consumed


class RoundTripError(JobError):
    """The card read from asmDB did not decode to the generated card."""


class RollbackError(JobError):
    """Compensation could not remove every row after a semantic mismatch."""
