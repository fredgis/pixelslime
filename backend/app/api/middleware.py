"""Pure-ASGI middleware: security headers and per-IP rate limiting.

These are written as raw ASGI apps rather than ``BaseHTTPMiddleware`` so they never
buffer streaming image responses. There is deliberately **no CORS middleware** — the
SPA is served same-origin, so cross-origin requests have no business succeeding.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from math import ceil

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.rate_limit import TokenBucketRateLimiter

#: A strict, same-origin CSP. Google Fonts is the one third party the design allows
#: (``contracts/design-tokens.json``); everything else is ``'self'``.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "img-src 'self' data:",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "script-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
    ]
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}

#: One year. Only ever applied to responses whose URL changes when the bytes change.
_IMMUTABLE = "public, max-age=31536000, immutable"

#: Suffixes of the media routes. A card is minted once and its hash is committed
#: on-chain, so the pixels behind these URLs can never change - which makes them the
#: one part of ``/api`` that is safe, and very much worth, caching hard.
_MEDIA_SUFFIXES = ("/image", "/thumb")


def _cache_control_for(path: str) -> str:
    """Decide the caching rule for a path.

    Serving nothing at all was the previous policy, and it inverted every case that
    matters. With no directive a cache may store a response and reuse it on its own
    terms, so ``/api/cards/today`` - the one payload that is different tomorrow - was
    the thing most likely to be served stale, while the hashed bundles that *can* be
    kept for a year were being re-validated every few hours. This function states the
    intent explicitly instead of leaving it to heuristics.
    """
    if path.startswith("/assets/") or path.endswith(_MEDIA_SUFFIXES):
        return _IMMUTABLE
    if path.startswith("/api/"):
        # Daily data. ``no-store`` rather than ``no-cache`` because these responses
        # carry no validator, so a revalidation would be a full refetch anyway, and
        # because a shared proxy holding yesterday's card is the exact failure this
        # replaces.
        return "no-store"
    # index.html and every SPA route that falls back to it. It is small, it has an
    # ETag, and it names the hashed bundles - so it must be checked every time or a
    # visitor can keep booting a build that no longer exists.
    return "no-cache"


class CacheControlMiddleware:
    """Give every response an explicit caching rule.

    ``setdefault`` rather than assignment: a route that has thought about its own
    caching keeps its answer, and this only fills the silence.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        directive = _cache_control_for(scope.get("path", ""))

        async def send_with_cache(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).setdefault("Cache-Control", directive)
            await send(message)

        await self.app(scope, receive, send_with_cache)


class SecurityHeadersMiddleware:
    """Attach a fixed set of security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _client_ip(scope: Scope, trust_forwarded_for: bool) -> str:
    """Best-effort client IP: the first X-Forwarded-For hop, else the socket peer."""
    if trust_forwarded_for:
        headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", ())
        for name, value in headers:
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first
    client: tuple[str, int] | None = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Token-bucket limiter keyed on client IP, applied only to ``/api`` routes."""

    def __init__(
        self,
        app: ASGIApp,
        limiter: TokenBucketRateLimiter,
        *,
        trust_forwarded_for: bool = True,
        exempt_paths: frozenset[str] = frozenset({"/api/health"}),
    ) -> None:
        self.app = app
        self._limiter = limiter
        self._trust_forwarded_for = trust_forwarded_for
        self._exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if not path.startswith("/api/") or path in self._exempt_paths:
            await self.app(scope, receive, send)
            return

        key = _client_ip(scope, self._trust_forwarded_for)
        result = await self._limiter.check(key)
        if result.allowed:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {"error": {"code": "rate_limited", "message": "Too many requests"}}
        ).encode("utf-8")
        retry_after = str(max(1, ceil(result.retry_after)))
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                    (b"retry-after", retry_after.encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
