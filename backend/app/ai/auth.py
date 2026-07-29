"""Entra-only auth and the shared httpx client for the AI endpoint.

API-key auth is disabled on the ``fgi`` resource (``docs/PLAN.md`` §1.1), so every
request carries a bearer token from ``DefaultAzureCredential`` scoped to
``https://cognitiveservices.azure.com/.default``. The token is injected by an
``httpx.Auth`` flow so individual call sites never see it and it is never logged,
per ``docs/AGENTS.md`` → Secrets.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

import httpx

from .config import API_BASE_URL, TOKEN_SCOPE

#: An async callable returning a fresh (or cached) bearer token string.
TokenProvider = Callable[[], Awaitable[str]]


class BearerTokenAuth(httpx.Auth):
    """Attach ``Authorization: Bearer <token>`` from an async token provider."""

    def __init__(self, token_provider: TokenProvider) -> None:
        self._token_provider = token_provider

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._token_provider()
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def azure_token_provider(scope: str = TOKEN_SCOPE) -> TokenProvider:
    """Return a token provider backed by ``DefaultAzureCredential`` (async).

    Imported lazily so that offline tests, which inject their own provider, do
    not need the Azure identity stack or any real credentials present.
    """
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()

    async def _provide() -> str:
        access_token = await credential.get_token(scope)
        return access_token.token

    return _provide


def build_async_client(
    token_provider: TokenProvider,
    *,
    base_url: str = API_BASE_URL,
    timeout: float = 300.0,
) -> httpx.AsyncClient:
    """Build the shared client.

    The read timeout is deliberately generous: a 1024x1536 ``quality=high``
    generation legitimately takes tens of seconds, and timing it out would turn
    a slow-but-successful call into a spurious failure.
    """
    return httpx.AsyncClient(
        base_url=base_url,
        auth=BearerTokenAuth(token_provider),
        timeout=httpx.Timeout(timeout, connect=15.0),
    )
