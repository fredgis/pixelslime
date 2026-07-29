"""Image proxy routes.

Blob Storage is private (``infra/modules/storage.bicep`` disables public access), so
the PNG and WebP are streamed through here. They are immutable once minted, so we set
a one-year ``immutable`` cache and honour conditional requests with a strong ``ETag``
so browsers and CDNs revalidate for free with a ``304``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.storage.blob import BlobDownload, BlobNotFound

from .deps import BlobDep, IndexDep
from .errors import ApiError
from .params import SerialPath

router = APIRouter(prefix="/api", tags=["media"])

CACHE_CONTROL = "public, max-age=31536000, immutable"


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """RFC 9110 ``If-None-Match`` check: ``*`` or a (weak-tolerant) token match."""
    want = etag.strip('"')
    for raw in if_none_match.split(","):
        candidate = raw.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate.strip('"') == want:
            return True
    return False


def _respond(download: BlobDownload, request: Request) -> Response:
    """Return the bytes, or a bare ``304`` when the client's ETag still matches."""
    etag = f'"{download.etag}"'
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None and _etag_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=download.data, media_type=download.content_type, headers=headers)


@router.get("/cards/{serial}/image")
async def get_card_image(
    request: Request, index: IndexDep, blob: BlobDep, serial: SerialPath
) -> Response:
    """Proxy the full-resolution card PNG from private storage."""
    if not index.contains(serial):
        raise ApiError(404, "card_not_found", f"No card with serial {serial}")
    try:
        download = await blob.get_card_png(serial)
    except BlobNotFound as exc:
        raise ApiError(404, "image_not_found", f"No image for serial {serial}") from exc
    return _respond(download, request)


@router.get("/cards/{serial}/thumb")
async def get_card_thumb(
    request: Request, index: IndexDep, blob: BlobDep, serial: SerialPath
) -> Response:
    """Proxy the WebP thumbnail from private storage."""
    if not index.contains(serial):
        raise ApiError(404, "card_not_found", f"No card with serial {serial}")
    try:
        download = await blob.get_thumb(serial)
    except BlobNotFound as exc:
        raise ApiError(404, "thumb_not_found", f"No thumbnail for serial {serial}") from exc
    return _respond(download, request)
