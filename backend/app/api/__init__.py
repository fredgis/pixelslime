"""The HTTP surface: routers, error envelope, middleware and SPA hosting.

Each concern in ``contracts/openapi.yaml`` gets its own router — ``routes_cards``
(gallery + provenance), ``routes_media`` (image proxy), ``routes_meta`` (health,
stats, NFT, admin) — wired together in :mod:`app.main`.
"""

from __future__ import annotations

from . import routes_cards, routes_media, routes_meta
from .errors import ApiError, install_error_handlers
from .middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from .spa import mount_spa

__all__ = [
    "ApiError",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "install_error_handlers",
    "mount_spa",
    "routes_cards",
    "routes_media",
    "routes_meta",
]
