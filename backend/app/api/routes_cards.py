"""The gallery and provenance routes — everything served from the in-memory index.

None of these handlers touch asmDB or the blob store: the index answers pagination,
filtering, sorting, search, the single card, "today", and even the ``/raw``
provenance view (which re-encodes the stored card through the real codec). That is
the whole point of ``docs/PLAN.md`` §4.6 — the hot path is memory only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.serialize import card_detail, card_summary, raw_view
from app.core.time import iso_utc, next_bloom_at, seconds_until_next_bloom

from .deps import IndexDep
from .errors import ApiError
from .params import (
    PageParam,
    RarityQueryParam,
    SearchParam,
    SerialPath,
    SizeParam,
    SortQueryParam,
    TypeParam,
)

router = APIRouter(prefix="/api", tags=["cards"])


# NOTE: /cards/today MUST be declared before /cards/{serial}; otherwise "today"
# is matched by the {serial} route and rejected as a non-integer.
@router.get("/cards/today")
async def get_today(index: IndexDep) -> dict[str, Any]:
    """Return today's card plus the countdown to the next 10:00 Europe/Paris bloom."""
    card = index.today()
    if card is None:
        raise ApiError(404, "no_card_today", "No card has bloomed today yet")
    return {
        "card": card_detail(card),
        "nextBloomAt": iso_utc(next_bloom_at()),
        "secondsUntilNext": seconds_until_next_bloom(),
        "dayNumber": index.size,
    }


@router.get("/cards")
async def list_cards(
    index: IndexDep,
    page: PageParam = 1,
    size: SizeParam = 24,
    type_: TypeParam = None,
    rarity: RarityQueryParam = None,
    sort: SortQueryParam = "newest",
    q: SearchParam = None,
) -> dict[str, Any]:
    """Return a filtered, sorted, paginated page of card summaries."""
    result = index.query(page=page, size=size, type_=type_, rarity=rarity, sort=sort, q=q)
    return {
        "items": [card_summary(card) for card in result.items],
        "page": result.page,
        "size": result.size,
        "total": result.total,
        "hasMore": result.has_more,
    }


@router.get("/cards/{serial}")
async def get_card(index: IndexDep, serial: SerialPath) -> dict[str, Any]:
    """Return one fully decoded card."""
    card = index.get(serial)
    if card is None:
        raise ApiError(404, "card_not_found", f"No card with serial {serial}")
    return card_detail(card)


@router.get("/cards/{serial}/raw")
async def get_card_raw(index: IndexDep, serial: SerialPath) -> dict[str, Any]:
    """Return the PSC-1 rows exactly as asmDB stores them, plus their decoding."""
    card = index.get(serial)
    if card is None:
        raise ApiError(404, "card_not_found", f"No card with serial {serial}")
    return raw_view(card)
