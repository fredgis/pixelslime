"""Structured logging for the backend: JSON to stdout, one event per line.

``docs/AGENTS.md`` is explicit: ``structlog``, JSON to stdout, the **card serial
bound on every card operation** so a bad day can be reconstructed, and the asmDB
bearer / Key Vault secrets **never** logged. This module owns the first three; the
last is enforced by never handing a secret to a logger in the first place
(:mod:`app.core.secrets`).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import structlog

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Install a JSON ``structlog`` pipeline once, idempotently.

    Idempotent because both the app lifespan and a bare ``import`` in tests may
    call it; re-running the processor chain would merely duplicate work.
    """
    global _configured
    if _configured:
        return

    numeric_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger; configures a sane default if startup has not run."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)  # type: ignore[no-any-return]


@contextmanager
def card_context(serial: int) -> Iterator[None]:
    """Bind ``serial`` for the duration of a card operation, then unbind it.

    Uses context vars so the serial rides along with every log line emitted while
    a request or job step is handling that card, which is the whole point of the
    convention in ``docs/AGENTS.md``.
    """
    structlog.contextvars.bind_contextvars(serial=serial)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars("serial")
