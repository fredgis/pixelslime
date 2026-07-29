"""Small dependency seams shared by daily, backfill and seed commands."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.ai import MintedCard
from app.asmdb import Row as AsmDbRow
from app.codec import Card
from app.storage.blob import BlobStore

Sleeper = Callable[[float], Awaitable[None]]
MonotonicClock = Callable[[], float]
MetricProperties = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GeneratedCard:
    """Canonical card state and the two blobs that must precede its rows."""

    card: Card
    png_bytes: bytes
    thumbnail_webp: bytes


class CardGenerator(Protocol):
    """Pure pipeline boundary used by orchestration and replaced by a test stub."""

    async def __call__(
        self,
        *,
        mint_day: int,
        serial: int,
        history: Sequence[MintedCard],
        used_names: Sequence[str],
        forced_rarity: str | None = None,
        is_seed: bool = False,
    ) -> GeneratedCard: ...


class JobRepository(Protocol):
    """The W3 card repository surface needed by write-side jobs."""

    async def write_card_rows(self, rows: Iterable[AsmDbRow]) -> list[AsmDbRow]: ...

    async def read_card_rows(self, serial: int) -> list[AsmDbRow]: ...

    async def find_card_by_date(self, yyyymmdd: int) -> AsmDbRow: ...

    async def list_card_serials(self) -> list[int]: ...


class AsmDbControl(Protocol):
    """Operations intentionally kept on W3's lower-level client."""

    async def warm(self, *, timeout: float | None = None) -> object: ...  # noqa: ASYNC109

    async def delete(self, row_id: int) -> None: ...


class MetricRecorder(Protocol):
    """Synchronous buffer boundary; production flushes it before process exit."""

    def record(
        self,
        name: str,
        value: float,
        properties: MetricProperties,
    ) -> None: ...


class NoOpMetricRecorder:
    """Avoid conditionals in tests and local injected dependency graphs."""

    def record(
        self,
        name: str,
        value: float,
        properties: MetricProperties,
    ) -> None:
        del name, value, properties


NOOP_METRICS = NoOpMetricRecorder()


@dataclass(frozen=True, slots=True)
class JobDependencies:
    """Injected boundaries make every job runnable without network side effects."""

    control: AsmDbControl
    repository: JobRepository
    blob: BlobStore
    generator: CardGenerator
    sleep: Sleeper = asyncio.sleep
    monotonic: MonotonicClock = time.perf_counter
    metrics: MetricRecorder = NOOP_METRICS
