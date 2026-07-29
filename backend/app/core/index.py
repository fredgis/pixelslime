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

from .chain import ChainAnchor, chain_from_storage_dict, chain_storage_dict
from .logging import get_logger
from .economy import (
    BLOOM_FEE,
    GENESIS_RAIN_TOTAL,
    MAX_BLOOMS,
    genesis_burned,
    genesis_remaining,
    smile_yield,
)
from .source import CardSource
from .time import mint_date, paris_today, yyyymmdd

_log = get_logger(__name__)

__all__ = ["BLOOM_FEE", "GENESIS_RAIN_TOTAL", "MAX_BLOOMS", "CardIndex"]

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
    #: Decoded ``part = 8`` anchor, or ``None`` when the card has no anchor row.
    #: The single source of truth for both the summary and detail ``onChain`` (D2).
    chain: ChainAnchor | None = None


@dataclass(frozen=True)
class CardPage:
    """One page of gallery results, matching the ``/api/cards`` envelope."""

    items: list[Card]
    page: int
    size: int
    total: int
    has_more: bool


def _entry(card: Card, chain: ChainAnchor | None = None) -> IndexEntry:
    day = mint_date(card.mint_day)
    return IndexEntry(
        card=card,
        mint_on=day,
        yyyymmdd=yyyymmdd(day),
        rarity_ordinal=RARITIES.index(card.rarity),
        chain=chain,
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
    def upsert(self, card: Card, chain: ChainAnchor | None = None) -> None:
        """Insert or replace a card and keep the date index consistent."""
        entry = _entry(card, chain)
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
        skipped rather than aborting the whole rebuild. The card's on-chain anchor
        (part 8) is read at the same time so ``chain`` is captured off the hot path.
        """
        for serial in await source.list_serials():
            if serial in self._by_serial:
                continue
            try:
                card = await source.read_card(serial)
            except (AsmDbError, CodecError) as exc:
                _log.warning("card_read_failed", serial=serial, error=str(exc))
                continue
            self.upsert(card, await _read_chain(source, serial))

    async def refresh_chain(self, source: CardSource, serial: int) -> bool:
        """Re-read one serial's anchor row and fold its chain state into the live index.

        The *targeted* counterpart to a full rebuild. Minting and anchoring are
        decoupled (``docs/PLAN.md`` §8.13): a card is indexed on the day it blooms and
        its ``part = 8`` row lands some days later, so the add-only :meth:`reconcile`
        never revisits it. This refreshes exactly that card's ``chain`` / ``onChain``
        off the hot path — no restart, no rescan of the collection — and is what W8
        calls after a successful anchor. Returns ``True`` once the serial is present.
        """
        card = self.get(serial)
        if card is None:
            try:
                card = await source.read_card(serial)
            except (AsmDbError, CodecError) as exc:
                _log.warning("refresh_chain_read_failed", serial=serial, error=str(exc))
                return False
        was_anchored = self.chain_for(serial) is not None
        chain = await _read_chain(source, serial)
        self.upsert(card, chain)
        if (chain is not None) != was_anchored:
            _log.info("chain_refreshed", serial=serial, on_chain=chain is not None)
        return True

    async def refresh_pending_anchors(self, source: CardSource) -> int:
        """Re-poll only the cards mid-anchor — header claims on-chain, no row read yet.

        Closes the asynchronous-anchor staleness gap for the running app without a full
        rescan. ``flags.on_chain`` is used *only* to pick which serials to re-read; the
        decoded anchor row stays the sole source of truth for ``onChain`` (D2), so the
        poll set is bounded to cards whose row is expected imminently and drains itself
        as those rows land. Returns the number newly anchored on this pass.
        """
        pending = [
            serial
            for serial, entry in self._by_serial.items()
            if entry.chain is None and entry.card.flags.on_chain
        ]
        updated = 0
        for serial in pending:
            await self.refresh_chain(source, serial)
            if self.chain_for(serial) is not None:
                updated += 1
        if updated:
            _log.info("pending_anchors_refreshed", refreshed=updated, pending=len(pending))
        return updated

    async def refresh_unanchored(self, source: CardSource, limit: int = 256) -> int:
        """Sweep cards that carry no anchor yet, ignoring ``flags.on_chain``.

        :meth:`refresh_pending_anchors` bounds its work by trusting that flag, which
        holds while minting and anchoring belong to one lifecycle. It stops holding
        the moment a chain is introduced to a collection that already exists: those
        cards were encoded with the flag clear, and it cannot be corrected afterwards
        because ``flags`` is part of the hashed stream — flipping the bit would change
        ``cardHash`` and invalidate the commitment already published on-chain.

        So this sweep asks the evidence instead of the hint. It is meant for startup,
        where the cost is paid once, and it is capped so that a long unanchored tail
        can never stall a boot. Returns the number newly anchored on this pass.
        """
        unanchored = [
            serial for serial, entry in self._by_serial.items() if entry.chain is None
        ][:limit]
        updated = 0
        for serial in unanchored:
            await self.refresh_chain(source, serial)
            if self.chain_for(serial) is not None:
                updated += 1
        if updated:
            _log.info("unanchored_sweep", refreshed=updated, scanned=len(unanchored))
        return updated

    # ── reads ───────────────────────────────────────────────────────────────
    @property
    def size(self) -> int:
        return len(self._by_serial)

    def get(self, serial: int) -> Card | None:
        entry = self._by_serial.get(serial)
        return entry.card if entry is not None else None

    def chain_for(self, serial: int) -> ChainAnchor | None:
        """Return the decoded on-chain anchor for a serial, or ``None`` if unanchored.

        Read straight from the pre-built entry so the gallery summary and the card
        detail resolve ``onChain`` from the *same* fact and can never disagree (D2).
        """
        entry = self._by_serial.get(serial)
        return entry.chain if entry is not None else None

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
        pool = 0
        for entry in self._by_serial.values():
            by_rarity[entry.card.rarity] += 1
            by_type[entry.card.type] += 1
            pool += smile_yield(entry.card)
        total = self.size
        return {
            "total": total,
            "byRarity": by_rarity,
            "byType": by_type,
            "genesisRemaining": genesis_remaining(total),
            "genesisBurned": genesis_burned(total),
            "genesisTotal": GENESIS_RAIN_TOTAL,
            "poolTotal": pool,
            "bloomsRemaining": max(0, MAX_BLOOMS - total),
        }

    # ── persistence ─────────────────────────────────────────────────────────
    def to_json_bytes(self) -> bytes:
        """Serialise the whole index to the ``index.json`` projection bytes.

        Each entry carries its decoded anchor so a warm restart keeps a card's
        on-chain status without re-reading asmDB (the reconcile only adds *new*
        serials, so chain would otherwise be lost on the second boot).
        """
        generated = self._generated_at or datetime.now(tz=UTC)
        payload = {
            "version": 2,
            "generatedAt": generated.isoformat(),
            "cards": [
                {
                    "card": entry.card.model_dump(mode="json"),
                    "chain": chain_storage_dict(entry.chain) if entry.chain is not None else None,
                }
                for entry in self._by_serial.values()
            ],
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def load_json_bytes(self, data: bytes) -> None:
        """Populate the index from ``index.json`` bytes. Raises on malformed input.

        Accepts both the current ``{"card": ..., "chain": ...}`` entries and the
        older flat card-dump entries (chain then resolves to ``None``).
        """
        doc = json.loads(data)
        cards = doc.get("cards", [])
        if not isinstance(cards, list):
            raise ValueError("index.json 'cards' must be a list")
        self._by_serial.clear()
        self._by_date.clear()
        for item in cards:
            if isinstance(item, dict) and "card" in item:
                card = Card.model_validate(item["card"])
                chain = chain_from_storage_dict(item.get("chain"))
            else:
                card = Card.model_validate(item)
                chain = None
            self.upsert(card, chain)
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


async def _read_chain(source: CardSource, serial: int) -> ChainAnchor | None:
    """Read a card's anchor off the hot path, degrading to unanchored on any failure.

    The absence of a decodable anchor row means "not anchored"; an asmDB hiccup on the
    anchor read must not fail the card's indexing, so it is logged and treated as such.
    """
    try:
        return await source.read_chain(serial)
    except (AsmDbError, CodecError) as exc:
        _log.warning("chain_read_failed", serial=serial, error=str(exc))
        return None


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
            # reconcile is add-only, so a card already in the index never has its
            # anchor re-read. Sweeping here is what makes a retroactive anchor visible
            # without a full rebuild.
            await index.refresh_unanchored(source)
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
