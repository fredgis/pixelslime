"""Local pytest registration for workstream-owned markers."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the live marker without changing the shared project configuration."""
    config.addinivalue_line(
        "markers",
        "integration: exercises a real external service and is opt-in",
    )
