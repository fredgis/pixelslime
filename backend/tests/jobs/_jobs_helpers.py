"""Workstream-local fakes for the jobs tests.

The module name is deliberately unique: pytest puts test directories on
``sys.path``, so a generic ``_helpers.py`` can collide with another workstream.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.ai import MintedCard
from app.asmdb import AsmDbError, AsmDbNotFound
from app.asmdb import Row as AsmDbRow
from app.codec import RARITIES, Card, Flags, Row, decode, encode
from app.jobs.models import GeneratedCard, JobDependencies
from app.storage.blob import BlobDownload, BlobNotFound

if TYPE_CHECKING:
    from pathlib import Path


def build_card(
    serial: int,
    mint_day: int,
    *,
    rarity: str = "COMMON",
    name: str | None = None,
    seed: bool = False,
) -> Card:
    """Build a compact, independently-known valid PSC-1 card."""
    return Card.model_validate(
        {
            "series": "PS",
            "serial": serial,
            "name": name or f"Slime{serial}",
            "level": 12,
            "rarity": rarity,
            "type": "FAIRY",
            "height_mm": 280,
            "weight_g": 900,
            "strength": 28,
            "endurance": 55,
            "agility": 65,
            "happiness": 95,
            "art_id": 1,
            "style_id": 1,
            "frame_id": RARITIES.index(rarity),
            "background_id": 7,
            "biome_id": 4,
            "mood_id": 2,
            "personality": "Cheerful and round.",
            "power_name": "Happy Bounce",
            "power_desc": "Bounces nearby friends safely.",
            "quote": "Boing!",
            "mint_day": mint_day,
            "shiny": False,
            "flags": Flags(verified=True, seed=seed),
            "art_sha": "01234567",
        }
    )


def _asm_rows(card: Card) -> list[AsmDbRow]:
    return [
        AsmDbRow(id=row.id, value=row.value, tag=row.tag, content=row.content)
        for row in encode(card)
    ]


def _codec_rows(rows: Iterable[AsmDbRow]) -> list[Row]:
    return [Row(id=row.id, value=row.value, tag=row.tag, content=row.content) for row in rows]


@dataclass
class FakeClock:
    """A deterministic monotonic clock whose sleep advances immediately."""

    value: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class FakeAsmDb:
    """In-memory asmDB fake with the service's row-content constraints."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.rows: dict[int, AsmDbRow] = {}
        self.warm_error: Exception | None = None
        self.write_error: Exception | None = None
        self.delete_error: AsmDbError | None = None
        self.corrupt_read_back = False
        self._corrupt_after_write = False

    def seed(self, card: Card) -> None:
        for row in _asm_rows(card):
            self.rows[row.id] = row

    async def warm(self, *, timeout: float | None = None) -> object:  # noqa: ASYNC109
        del timeout
        self.events.append("asmdb.warm")
        if self.warm_error is not None:
            raise self.warm_error
        return object()

    async def delete(self, row_id: int) -> None:
        self.events.append(f"asmdb.delete:{row_id}")
        if self.delete_error is not None:
            raise self.delete_error
        if row_id not in self.rows:
            raise AsmDbNotFound("missing row", code="not_found", status_code=404)
        del self.rows[row_id]

    async def find_card_by_date(self, yyyymmdd: int) -> AsmDbRow:
        self.events.append(f"rows.find:{yyyymmdd}")
        matches = [row for row in self.rows.values() if row.id % 16 == 0 and row.value == yyyymmdd]
        if not matches:
            raise AsmDbNotFound("missing date", code="not_found", status_code=404)
        if len(matches) != 1:
            raise AsmDbError("duplicate date", code="duplicate_card_date")
        return matches[0]

    async def list_card_serials(self) -> list[int]:
        self.events.append("rows.list")
        return sorted(row.id // 16 for row in self.rows.values() if row.id % 16 == 0)

    async def write_card_rows(self, rows: Iterable[AsmDbRow]) -> list[AsmDbRow]:
        self.events.append("rows.write")
        pending = list(rows)
        if self.write_error is not None:
            raise self.write_error
        for row in pending:
            encoded = row.content.encode("utf-8")
            if len(encoded) > 175 or any(byte in encoded for byte in (0, 10, 13)):
                raise AsmDbError("fake rejected invalid row content", code="invalid_row")
            if row.id in self.rows:
                raise AsmDbError("row already exists", code="already_exists")
        for row in pending:
            self.rows[row.id] = row
        self._corrupt_after_write = self.corrupt_read_back
        return pending

    async def read_card_rows(self, serial: int) -> list[AsmDbRow]:
        self.events.append(f"rows.read:{serial}")
        stored = sorted(
            (row for row in self.rows.values() if row.id // 16 == serial and row.id % 16 < 4),
            key=lambda row: row.id,
        )
        if not stored:
            raise AsmDbNotFound("missing serial", code="not_found", status_code=404)
        if self._corrupt_after_write:
            original = decode(_codec_rows(stored))
            corrupt = original.model_copy(update={"happiness": (original.happiness + 1) % 101})
            return _asm_rows(corrupt)
        return stored


class FakeBlobStore:
    """Blob fake that records ordering and can fail each write boundary."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.cards: dict[int, bytes] = {}
        self.thumbs: dict[int, bytes] = {}
        self.index: bytes | None = None
        self.put_error: Exception | None = None
        self.index_error: Exception | None = None

    async def get_card_png(self, serial: int) -> BlobDownload:
        try:
            data = self.cards[serial]
        except KeyError as exc:
            raise BlobNotFound(str(serial)) from exc
        return BlobDownload(data=data, etag="fake", content_type="image/png")

    async def get_thumb(self, serial: int) -> BlobDownload:
        try:
            data = self.thumbs[serial]
        except KeyError as exc:
            raise BlobNotFound(str(serial)) from exc
        return BlobDownload(data=data, etag="fake", content_type="image/webp")

    async def put_card(self, serial: int, png: bytes, webp: bytes) -> None:
        self.events.append(f"blob.put:{serial}")
        if self.put_error is not None:
            raise self.put_error
        self.cards[serial] = png
        self.thumbs[serial] = webp

    async def load_index(self) -> bytes | None:
        return self.index

    async def save_index(self, data: bytes) -> None:
        self.events.append("blob.index")
        if self.index_error is not None:
            raise self.index_error
        self.index = data

    async def aclose(self) -> None:
        return None


class StubGenerator:
    """Pipeline seam returning deterministic cards or queued failures."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.failures: list[Exception] = []
        self.calls: list[dict[str, object]] = []

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
        self.events.append(f"generate:{serial}")
        self.calls.append(
            {
                "mint_day": mint_day,
                "serial": serial,
                "history": tuple(history),
                "used_names": tuple(used_names),
                "forced_rarity": forced_rarity,
                "is_seed": is_seed,
            }
        )
        if self.failures:
            raise self.failures.pop(0)
        rarity = forced_rarity or "COMMON"
        return GeneratedCard(
            card=build_card(serial, mint_day, rarity=rarity, seed=is_seed),
            png_bytes=f"png-{serial}".encode(),
            thumbnail_webp=f"webp-{serial}".encode(),
        )


class FakeMetricRecorder:
    """Capture custom measurements without an ingestion endpoint."""

    def __init__(self) -> None:
        self.records: list[tuple[str, float, dict[str, object]]] = []

    def record(
        self,
        name: str,
        value: float,
        properties: Mapping[str, object],
    ) -> None:
        self.records.append((name, value, dict(properties)))


@dataclass
class FakeEnvironment:
    events: list[str]
    asmdb: FakeAsmDb
    blob: FakeBlobStore
    generator: StubGenerator
    clock: FakeClock
    metrics: FakeMetricRecorder
    deps: JobDependencies


def fake_environment() -> FakeEnvironment:
    events: list[str] = []
    asmdb = FakeAsmDb(events)
    blob = FakeBlobStore(events)
    generator = StubGenerator(events)
    clock = FakeClock()
    metrics = FakeMetricRecorder()
    deps = JobDependencies(
        control=asmdb,
        repository=asmdb,
        blob=blob,
        generator=generator,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        metrics=metrics,
    )
    return FakeEnvironment(events, asmdb, blob, generator, clock, metrics, deps)


def repo_root_from(path: Path) -> Path:
    """Find the repository root for tests that exercise default seed assets."""
    for parent in path.resolve().parents:
        if (parent / "contracts" / "card.schema.json").is_file():
            return parent
    raise AssertionError("repository root not found")
