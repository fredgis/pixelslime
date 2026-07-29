"""Serve the built SPA with a history-API fallback.

W6's Vite build lands in ``frontend/dist``. We serve real files when they exist and
fall back to ``index.html`` for client-side routes so a refresh on ``/slime/42``
works. The catch-all is registered *after* the API routers and explicitly refuses
anything under ``/api`` so a mistyped endpoint 404s as JSON instead of being handed
the SPA shell. A missing ``dist`` (W6 hasn't built yet) is tolerated: no route is
added and the API still runs.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response

from app.core.logging import get_logger

from .errors import ApiError

_log = get_logger(__name__)


def mount_spa(app: FastAPI, dist_dir: Path | None) -> None:
    """Register the SPA fallback if a built ``dist`` with an ``index.html`` exists."""
    if dist_dir is None or not dist_dir.is_dir():
        _log.info("spa_dist_absent", path=str(dist_dir) if dist_dir else None)
        return
    index_html = dist_dir / "index.html"
    if not index_html.is_file():
        _log.info("spa_index_absent", path=str(index_html))
        return

    root = dist_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            raise ApiError(404, "not_found", "No such endpoint")
        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index_html)

    _log.info("spa_mounted", path=str(root))
