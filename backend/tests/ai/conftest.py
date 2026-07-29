"""Pytest bootstrap and fixtures for the W4 AI pipeline tests.

Puts the backend root and this directory on ``sys.path`` (mirroring
``tests/codec/conftest.py``) so ``import app.ai`` and the flat ``_helpers`` module
both resolve however pytest is launched, and provides the offline HTTP client
every network test drives through ``respx``.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_TESTDIR = _HERE.parent  # backend/tests/ai/

for _p in (str(_BACKEND), str(_TESTDIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.ai.auth import build_async_client  # noqa: E402
from app.ai.config import API_BASE_URL  # noqa: E402
from app.ai.prompt import MasterPrompt, load_master_prompt  # noqa: E402

BASE_URL = API_BASE_URL
CHAT_URL = f"{API_BASE_URL}chat/completions"
IMAGES_URL = f"{API_BASE_URL}images/edits"


async def _fake_token() -> str:
    return "test-token"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """A real ``httpx.AsyncClient`` (with the bearer flow) for respx to intercept."""
    async with build_async_client(_fake_token, timeout=5.0) as http_client:
        yield http_client


@pytest.fixture
def master_prompt() -> MasterPrompt:
    return load_master_prompt()
