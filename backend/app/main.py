"""The FastAPI application: wiring, lifespan and graceful degradation.

:func:`create_app` assembles the routers, the error envelope, the security and
rate-limit middleware and the SPA fallback. The lifespan loads secrets, picks a
backend (real Azure, or in-memory fakes for ``LOCAL_DEV``/tests), warms asmDB and
builds the in-memory index — degrading to a "still serving from the blob snapshot"
state instead of failing startup when asmDB is asleep.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from app.api import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    install_error_handlers,
    mount_spa,
    routes_cards,
    routes_media,
    routes_meta,
)
from app.asmdb import AsmDbError
from app.codec import Card, CodecError
from app.core.config import Settings, load_settings
from app.core.index import CardIndex, bootstrap_index
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import TokenBucketRateLimiter
from app.core.secrets import SecretProvider, load_secrets
from app.core.source import AsmDbCardSource, CardSource, InMemoryCardSource
from app.storage.blob import AzureBlobStore, BlobStore, InMemoryBlobStore

_log = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS_CARDS = _REPO_ROOT / "contracts" / "cards"


def _swatch(card: Card) -> tuple[int, int, int]:
    """A stable placeholder colour derived from the card's type and rarity."""
    h = abs(hash((card.type, card.rarity)))
    return (128 + h % 128, 64 + (h >> 8) % 160, 96 + (h >> 16) % 128)


def _placeholder_pair(card: Card) -> tuple[bytes, bytes]:
    """Tiny PNG + WebP stand-ins so the image routes have something to proxy locally."""
    from PIL import Image

    color = _swatch(card)
    png = io.BytesIO()
    Image.new("RGBA", (16, 24), (*color, 255)).save(png, format="PNG")
    thumb = io.BytesIO()
    try:
        Image.new("RGB", (12, 18), color).save(thumb, format="WEBP")
    except (OSError, KeyError, ValueError):
        Image.new("RGB", (12, 18), color).save(thumb, format="PNG")
    return png.getvalue(), thumb.getvalue()


def build_fakes() -> tuple[InMemoryCardSource, InMemoryBlobStore]:
    """Seed an in-memory backend from ``contracts/cards/*.json`` for offline runs."""
    source = InMemoryCardSource()
    blob = InMemoryBlobStore()
    seeded = 0
    for path in sorted(_CONTRACTS_CARDS.glob("*.json")):
        try:
            card = Card.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _log.warning("fake_seed_read_failed", file=path.name, error=str(exc))
            continue
        try:
            source.add_card(card)
        except (ValueError, CodecError) as exc:
            _log.warning("fake_seed_encode_failed", file=path.name, error=str(exc))
            continue
        png, webp = _placeholder_pair(card)
        blob.seed_card(card.serial, png, webp)
        seeded += 1
    _log.info("fakes_built", cards=seeded)
    return source, blob


def _build_backend(settings: Settings, secrets: SecretProvider) -> tuple[CardSource, BlobStore]:
    """Construct the real Azure-backed source and blob store."""
    if settings.asmdb_url is None:
        raise RuntimeError("ASMDB_BASE_URL must be set outside LOCAL_DEV")
    if settings.blob_service_url is None:
        raise RuntimeError("STORAGE_ACCOUNT_NAME or STORAGE_BLOB_ENDPOINT must be set")

    from app.asmdb import AsmDbClient

    client = AsmDbClient(settings.asmdb_url, secrets.asmdb_bearer_for_client())
    source: CardSource = AsmDbCardSource(client)
    blob: BlobStore = AzureBlobStore(
        settings.blob_service_url,
        cards_container=settings.cards_container,
        thumbs_container=settings.thumbs_container,
        assets_container=settings.assets_container,
        index_blob_name=settings.index_blob_name,
    )
    return source, blob


async def _reconcile_loop(
    settings: Settings,
    source: CardSource,
    blob: BlobStore,
    index: CardIndex,
    stop: asyncio.Event,
) -> None:
    """Periodically fold newly bloomed cards into the index without a restart."""
    while not stop.is_set():
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.index_refresh_seconds)
        if stop.is_set():
            return
        try:
            health = await source.health()
            index.engine = health.engine
            await index.reconcile(source)
            # refresh_unanchored, not refresh_pending_anchors. The latter polls only
            # cards whose header flags.on_chain is set, and that bit is written when the
            # card is created — before any anchor exists — so it is false on every card
            # and that sweep polls nothing at all. Anchoring lands roughly half an hour
            # after the bloom, long after this loop has already folded the card in, so
            # the anchor must be re-read from the evidence rather than predicted from a
            # flag. Without this a card stays ANCHOR PENDING until someone restarts.
            await index.refresh_unanchored(source)
            index.degraded = False
            await blob.save_index(index.to_json_bytes())
        except (AsmDbError, OSError, ValueError) as exc:
            _log.warning("reconcile_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load secrets, choose a backend, warm asmDB and build the index."""
    settings: Settings = app.state.settings
    injected_source: CardSource | None = app.state.injected_source
    injected_blob: BlobStore | None = app.state.injected_blob
    injected_secrets: SecretProvider | None = app.state.injected_secrets

    secrets = injected_secrets if injected_secrets is not None else await load_secrets(settings)
    app.state.secrets = secrets

    source: CardSource
    blob: BlobStore
    if injected_source is not None:
        source = injected_source
        blob = injected_blob if injected_blob is not None else InMemoryBlobStore()
    elif settings.use_fakes:
        source, blob = build_fakes()
    else:
        source, blob = _build_backend(settings, secrets)
    app.state.source = source
    app.state.blob = blob

    index = await bootstrap_index(source, blob)
    app.state.index = index
    _log.info("app_ready", cards=index.size, degraded=index.degraded, engine=index.engine)

    stop = asyncio.Event()
    task = asyncio.create_task(_reconcile_loop(settings, source, blob, index, stop))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await source.aclose()
        await blob.aclose()


def _resolve_dist(settings: Settings) -> Path:
    """Locate the built SPA; default to ``<repo>/frontend/dist``."""
    if settings.frontend_dist:
        return Path(settings.frontend_dist)
    return _REPO_ROOT / "frontend" / "dist"


def create_app(
    settings: Settings | None = None,
    *,
    source: CardSource | None = None,
    blob: BlobStore | None = None,
    secrets: SecretProvider | None = None,
) -> FastAPI:
    """Build the application. Injected ``source``/``blob``/``secrets`` power tests."""
    settings = settings if settings is not None else load_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PixelSlime API",
        version="1.0.0",
        description="Public, read-only API for the PixelSlime SLIMEDEX.",
        lifespan=lifespan,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.injected_source = source
    app.state.injected_blob = blob
    app.state.injected_secrets = secrets

    limiter = TokenBucketRateLimiter(
        settings.rate_limit_capacity, settings.rate_limit_refill_per_second
    )
    app.state.limiter = limiter

    app.include_router(routes_cards.router)
    app.include_router(routes_media.router)
    app.include_router(routes_meta.router)
    install_error_handlers(app)

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        trust_forwarded_for=settings.trust_forwarded_for,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    mount_spa(app, _resolve_dist(settings))
    return app


app = create_app()
