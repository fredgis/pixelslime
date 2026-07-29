"""The in-memory card index — the heart of the read path.

Every gallery query, the stats counters and "today's bloom" are served from here,
**never** from asmDB (``docs/PLAN.md`` §4.6: the gallery must not hit asmDB on the
hot path). asmDB stays the source of truth; this index is a rebuildable projection,
mirrored to an ``index.json`` blob.

Lifecycle:

* :func:`bootstrap_index` builds it at startup — from the ``index.json`` blob if
  present (fast), then reconciled against asmDB (authoritative), degrading rather
  than failing if asmDB is asleep.
* :meth:`CardIndex.upsert` folds in a freshly bloomed card without a restart.

The economy counters (``genesisRemaining`` / ``bloomsRemaining``) are a projection
of the card count onto the fixed ``docs/PLAN.md`` §8.6 constants; the authoritative
values live on-chain (W9). See the W7 report.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.asmdb import AsmDbError
from app.codec import RARITIES, TYPES, Card, CodecError

from .logging import get_logger
from .source import CardSource
from .time import mint_date, paris_today, yyyymmdd

_log = get_logger(__name__)

# ── Economy, from docs/PLAN.md §8.6 (the chain is the real ledger; W9) ───────
GENESIS_RAIN_TOTAL = 365_000
BLOOM_FEE = 100
MAX_BLOOMS = 3_650

SORTS = frozenset({"newest", "oldest", "rarest", "happiest"})


class IndexBlob(Protocol):
    """The two blob operations the index needs; satisfied by any blob store."""

    async def load_index(self) -> bytes | None: ...
    async def save_index(self, data: bytes) -> None: ...


@dataclass(frozen=True)
class IndexEntry:
    """A card plus the pre-computed keys the query paths sort and filter on."""

    card: Card
    mint_on: date
    yyyymmdd: int
    rarity_ordinal: int


@dataclass(frozen=True)
class CardPage:
    """One page of gallery results, matching the ``/api/cards`` envelope."""

    items: list[Card]
    page: int
    size: int
    total: int
    has_more: bool


def _entry(card: Card) -> IndexEntry:
    day = mint_date(card.mint_day)
    return IndexEntry(
        card=card,
        mint_on=day,
        yyyymmdd=yyyymmdd(day),
        rarity_ordinal=RARITIES.index(card.rarity),
    )


class CardIndex:
    """A serial-keyed projection of every card, with derived query structures."""

    def __init__(self) -> None:
        self._by_serial: dict[int, IndexEntry] = {}
        self._by_date: dict[int, int] = {}
        self._generated_at: datetime | None = None
        #: asmDB engine string, surfaced by ``/api/health``; unknown until reconciled.
        self.engine = "unknown"
        #: ``True`` until a successful asmDB reconcile; drives the health status.
        self.degraded = True

    # ── mutation ────────────────────────────────────────────────────────────
    def upsert(self, card: Card) -> None:
        """Insert or replace a card and keep the date index consistent."""
        entry = _entry(card)
        previous = self._by_serial.get(card.serial)
        if (
            previous is not None
            and previous.yyyymmdd != entry.yyyymmdd
            and self._by_date.get(previous.yyyymmdd) == card.serial
        ):
            del self._by_date[previous.yyyymmdd]

        self._by_serial[card.serial] = entry
        clash = self._by_date.get(entry.yyyymmdd)
        if clash is not None and clash != card.serial:
            _log.warning(
                "duplicate_bloom_date",
                yyyymmdd=entry.yyyymmdd,
                kept=max(clash, card.serial),
                dropped=min(clash, card.serial),
            )
            self._by_date[entry.yyyymmdd] = max(clash, card.serial)
        else:
            self._by_date[entry.yyyymmdd] = card.serial

    def replace_all(self, cards: Iterable[Card]) -> None:
        """Rebuild from scratch (used when loading a full ``index.json``)."""
        self._by_serial.clear()
        self._by_date.clear()
        for card in cards:
            self.upsert(card)

    async def reconcile(self, source: CardSource) -> None:
        """Fold in every serial asmDB has that the index is missing.

        Because the index.json base already carries known cards, a warm restart
        typically reads only the one card that bloomed since — the "fresher"
        fast-path from ``docs/PLAN.md`` §4.6. A single corrupt card is logged and
        skipped rather than aborting the whole rebuild.
        """
        for serial in await source.list_serials():
            if serial in self._by_serial:
                continue
            try:
                card = await source.read_card(serial)
            except (AsmDbError, CodecError) as exc:
                _log.warning("card_read_failed", serial=serial, error=str(exc))
                continue
            self.upsert(card)

    # ── reads ───────────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        return len(self._by_serial)

    def get(self, serial: int) -> Card | None:
        entry = self._by_serial.get(serial)
        return entry.card if entry is not None else None

    def contains(self, serial: int) -> bool:
        return serial in self._by_serial

    def today(self, now_utc: datetime | None = None) -> Card | None:
        """Return the card whose mint date is today in ``Europe/Paris``, or ``None``."""
        serial = self._by_date.get(yyyymmdd(paris_today(now_utc)))
        return self.get(serial) if serial is not None else None

    def query(
        self,
        *,
        page: int,
        size: int,
        type_: str | None = None,
        rarity: str | None = None,
        sort: str = "newest",
        q: str | None = None,
    ) -> CardPage:
        """Filter, sort and paginate the collection entirely in memory."""
        if sort not in SORTS:
            raise ValueError(f"unknown sort {sort!r}")

        entries = list(self._by_serial.values())
        if type_ is not None:
            entries = [e for e in entries if e.card.type == type_]
        if rarity is not None:
            entries = [e for e in entries if e.card.rarity == rarity]
        if q:
            needle = q.casefold()
            entries = [e for e in entries if needle in e.card.name.casefold()]

        entries.sort(key=_SORT_KEYS[sort], reverse=_SORT_REVERSE[sort])

        total = len(entries)
        start = (page - 1) * size
        window = entries[start : start + size]
        return CardPage(
            items=[e.card for e in window],
            page=page,
            size=size,
            total=total,
            has_more=start + size < total,
        )

    def stats(self) -> dict[str, Any]:
        """Collection-wide counters, including the economy projection (§8.6)."""
        by_rarity = dict.fromkeys(RARITIES, 0)
        by_type = dict.fromkeys(TYPES, 0)
        for entry in self._by_serial.values():
            by_rarity[entry.card.rarity] += 1
            by_type[entry.card.type] += 1
        total = self.size
        return {
            "total": total,
            "byRarity": by_rarity,
            "byType": by_type,
            "genesisRemaining": max(0, GENESIS_RAIN_TOTAL - total * BLOOM_FEE),
            "bloomsRemaining": max(0, MAX_BLOOMS - total),
        }

    # ── persistence ─────────────────────────────────────────────────────────
    def to_json_bytes(self) -> bytes:
        """Serialise the whole index to the ``index.json`` projection bytes."""
        generated = self._generated_at or datetime.now(tz=UTC)
        payload = {
            "version": 1,
            "generatedAt": generated.isoformat(),
            "cards": [entry.card.model_dump(mode="json") for entry in self._by_serial.values()],
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def load_json_bytes(self, data: bytes) -> None:
        """Populate the index from ``index.json`` bytes. Raises on malformed input."""
        doc = json.loads(data)
        cards = doc.get("cards", [])
        if not isinstance(cards, list):
            raise ValueError("index.json 'cards' must be a list")
        self.replace_all(Card.model_validate(card) for card in cards)
        generated = doc.get("generatedAt")
        if isinstance(generated, str):
            self._generated_at = datetime.fromisoformat(generated)


_SORT_KEYS: dict[str, Any] = {
    "newest": lambda e: (e.card.mint_day, e.card.serial),
    "oldest": lambda e: (e.card.mint_day, e.card.serial),
    "rarest": lambda e: (e.rarity_ordinal, e.card.mint_day, e.card.serial),
    "happiest": lambda e: (e.card.happiness, e.card.serial),
}
_SORT_REVERSE: dict[str, bool] = {
    "newest": True,
    "oldest": False,
    "rarest": True,
    "happiest": True,
}


async def bootstrap_index(
    source: CardSource,
    blob: IndexBlob | None = None,
) -> CardIndex:
    """Build the index at startup with graceful degradation.

    Order of preference: the ``index.json`` blob as a warm base, then an
    authoritative reconcile against asmDB. If asmDB is asleep the index still
    serves whatever the blob provided (marked degraded) instead of failing
    startup — the whole point of the warm-up dance in ``docs/AGENTS.md``.
    """
    index = CardIndex()

    source_ok = False
    try:
        health = await source.health()
        index.engine = health.engine
        source_ok = health.ok
    except AsmDbError as exc:
        _log.warning("source_health_failed", error=str(exc))

    if blob is not None:
        try:
            data = await blob.load_index()
        except (OSError, ValueError) as exc:
            _log.warning("index_blob_load_failed", error=str(exc))
        else:
            if data:
                try:
                    index.load_json_bytes(data)
                    _log.info("index_loaded_from_blob", cards=index.size)
                except (ValueError, CodecError) as exc:
                    _log.warning("index_blob_parse_failed", error=str(exc))

    if source_ok:
        try:
            await index.reconcile(source)
            index.degraded = False
            _log.info("index_reconciled", cards=index.size, engine=index.engine)
        except AsmDbError as exc:
            _log.warning("index_reconcile_failed", error=str(exc))
        else:
            if blob is not None:
                try:
                    await blob.save_index(index.to_json_bytes())
                except (OSError, ValueError) as exc:
                    _log.warning("index_blob_save_failed", error=str(exc))

    if index.degraded:
        _log.warning("index_degraded", cards=index.size, engine=index.engine)
    return index
