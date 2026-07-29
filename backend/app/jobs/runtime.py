"""Production wiring for W2/W3/W4/W7 dependencies used by job commands."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx

from app.ai import MintedCard, azure_token_provider, build_async_client, generate_card
from app.asmdb import AsmDbClient, AsmDbRepository
from app.codec import Card
from app.core.config import load_settings
from app.core.logging import configure_logging, get_logger
from app.core.secrets import load_secrets
from app.storage.blob import AzureBlobStore

from .models import NOOP_METRICS, GeneratedCard, JobDependencies, MetricRecorder
from .telemetry import AppInsightsMetricSink

_log = get_logger(__name__)

_IMAGE_LIMIT = 2
_IMAGE_WINDOW_SECONDS = 60.0
_IMAGE_PATH_SUFFIX = "/images/edits"

Sleeper = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class ImageRequestGate:
    """Enforce the real two-image-requests-per-rolling-minute limit.

    The gate sits at the HTTP ``post`` boundary, so it covers W4's internal 429
    retries and verification regeneration as well as separate backfill cards.
    """

    def __init__(
        self,
        *,
        limit: int = _IMAGE_LIMIT,
        window_seconds: float = _IMAGE_WINDOW_SECONDS,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        if limit < 1:
            raise ValueError("image request limit must be positive")
        if window_seconds <= 0:
            raise ValueError("image request window must be positive")
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until starting another image request cannot exceed the window."""
        async with self._lock:
            while True:
                now = self._clock()
                while self._starts and now - self._starts[0] >= self._window:
                    self._starts.popleft()
                if len(self._starts) < self._limit:
                    self._starts.append(now)
                    return
                wait = self._window - (now - self._starts[0])
                _log.info(
                    "image_request.rate_limit_wait",
                    wait_seconds=round(wait, 3),
                    requests_in_window=len(self._starts),
                )
                await self._sleep(wait)


class ImageRateLimitedClient:
    """Minimal proxy around httpx; W4 only needs its async ``post`` method."""

    def __init__(self, client: httpx.AsyncClient, gate: ImageRequestGate) -> None:
        self._client = client
        self._gate = gate

    async def post(self, url: str | httpx.URL, **kwargs: Any) -> httpx.Response:
        path = "/" + httpx.URL(url).path.strip("/")
        if path.endswith(_IMAGE_PATH_SUFFIX):
            await self._gate.acquire()
        return await self._client.post(url, **kwargs)


class PipelineCardGenerator:
    """Adapt W4's rich result to the canonical W2 card plus persisted blobs."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __call__(
        self,
        *,
        mint_day: int,
        serial: int,
        history: Sequence[MintedCard],
        used_names: Sequence[str],
        forced_rarity: str | None = None,
        is_seed: bool = False,
    ) -> GeneratedCard:
        result = await generate_card(
            mint_day=mint_day,
            serial=serial,
            client=self._client,
            history=history,
            used_names=used_names,
            forced_rarity=forced_rarity,
            is_seed=is_seed,
        )
        card = Card.model_validate(result.card)
        return GeneratedCard(
            card=card,
            png_bytes=result.png_bytes,
            thumbnail_webp=result.thumbnail_webp,
        )


@asynccontextmanager
async def production_dependencies() -> AsyncIterator[JobDependencies]:
    """Build and close every real boundary required by a one-shot job process."""
    settings = load_settings()
    configure_logging(settings.log_level)
    if settings.use_fakes:
        raise RuntimeError(
            "job commands require explicit injected fakes; production wiring cannot write "
            "through the API's read-only fake backend"
        )
    if settings.asmdb_url is None:
        raise RuntimeError("ASMDB_BASE_URL must be set for generation jobs")
    if settings.blob_service_url is None:
        raise RuntimeError(
            "STORAGE_ACCOUNT_NAME or STORAGE_BLOB_ENDPOINT must be set for generation jobs"
        )

    asmdb: AsmDbClient | None = None
    blob: AzureBlobStore | None = None
    ai_client: httpx.AsyncClient | None = None
    telemetry_client: httpx.AsyncClient | None = None
    metric_sink: MetricRecorder = NOOP_METRICS
    try:
        secrets = await load_secrets(settings)
        asmdb = AsmDbClient(settings.asmdb_url, secrets.asmdb_bearer_for_client())
        repository = AsmDbRepository(asmdb)
        blob = AzureBlobStore(
            settings.blob_service_url,
            cards_container=settings.cards_container,
            thumbs_container=settings.thumbs_container,
            assets_container=settings.assets_container,
            index_blob_name=settings.index_blob_name,
        )
        ai_client = build_async_client(azure_token_provider())
        if settings.applicationinsights_connection_string:
            telemetry_client = httpx.AsyncClient(timeout=10.0)
            metric_sink = AppInsightsMetricSink(
                settings.applicationinsights_connection_string,
                client=telemetry_client,
            )
        else:
            _log.warning("app_insights_metrics_disabled")

        gate = ImageRequestGate()
        gated_client = cast("httpx.AsyncClient", ImageRateLimitedClient(ai_client, gate))
        generator = PipelineCardGenerator(gated_client)
        yield JobDependencies(
            control=asmdb,
            repository=repository,
            blob=blob,
            generator=generator,
            metrics=metric_sink,
        )
    finally:
        if isinstance(metric_sink, AppInsightsMetricSink):
            try:
                await metric_sink.flush()
            except httpx.HTTPError as exc:
                _log.error(
                    "app_insights_metric_flush_failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        if telemetry_client is not None:
            await telemetry_client.aclose()
        if ai_client is not None:
            await ai_client.aclose()
        if blob is not None:
            await blob.aclose()
        if asmdb is not None:
            await asmdb.aclose()
