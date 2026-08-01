"""Opt-in checks against the public asmDB health route."""

from __future__ import annotations

import os

import httpx
import pytest

from app.asmdb import AsmDbClient

LIVE_BASE_URL = f"https://www.asmdb.cloud/db/{os.getenv('ASMDB_INSTANCE', '')}"
RUN_LIVE_HEALTH = os.getenv("ASMDB_RUN_LIVE_HEALTH") == "1"
TOKEN_PRESENT = bool(os.getenv("ASMDB_BEARER_TOKEN"))


@pytest.mark.integration
@pytest.mark.skipif(
    not (TOKEN_PRESENT or RUN_LIVE_HEALTH),
    reason=(
        "no bearer token is present; set ASMDB_RUN_LIVE_HEALTH=1 to run only "
        "the unauthenticated health check"
    ),
)
async def test_live_health_is_ready() -> None:
    """Confirm the public route exposes a live engine, not a mocked contract."""
    async with AsmDbClient(
        LIVE_BASE_URL,
        token=None,
        timeout=httpx.Timeout(70.0),
        warm_timeout=180.0,
        retry_attempts=10,
    ) as client:
        health = await client.warm()

    assert health.status == "ok"
    assert isinstance(health.engine, str)
    assert health.engine
