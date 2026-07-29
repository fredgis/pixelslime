"""Pure card → JSON projections for the API layer.

The router modules stay thin by delegating every shape in ``contracts/openapi.yaml``
to a function here: the gallery :func:`card_summary`, the full :func:`card_detail`,
the ERC-721 :func:`nft_metadata`, and the provenance :func:`raw_view`. None of
these touch the network — even ``raw_view`` re-derives the asmDB rows by *re-encoding*
the decoded card through the real codec, which is byte-identical to what asmDB
stores (the codec is deterministic) and so needs no round-trip.

Three schema fields are resolved from W4's frozen lookup tables
(``contracts/lookups.json``): ``biome`` from ``biome_id``, ``mood`` from ``mood_id``,
and ``companion`` from ``companion_id`` (only when ``flags.has_companion`` is set).
All three are declared ``nullable`` in the contract and are **always present as a
key**: an out-of-range id, or a card with no companion, resolves to ``null`` rather
than omitting the field, so the frontend can rely on a stable shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.codec import Card, card_hash, encode, encode_stream

from . import contracts
from .chain import ChainAnchor, chain_api_dict
from .time import mint_date


def card_id(serial: int) -> str:
    """Render the display id, e.g. ``PS-0001`` (``^PS-[0-9]{4,5}$``)."""
    return f"PS-{serial:04d}"


def image_url(serial: int) -> str:
    """Same-origin proxy path for the full PNG."""
    return f"/api/cards/{serial}/image"


def thumb_url(serial: int) -> str:
    """Same-origin proxy path for the WebP thumbnail."""
    return f"/api/cards/{serial}/thumb"


def _mint_date_iso(card: Card) -> str:
    return mint_date(card.mint_day).isoformat()


def card_summary(card: Card, *, chain: ChainAnchor | None = None) -> dict[str, Any]:
    """Project a card onto ``CardSummary`` — what the gallery grid needs, no more.

    ``onChain`` mirrors ``chain != null`` — i.e. whether a decodable anchor row
    exists — so the grid badge and the detail view can never disagree (D2). It is
    *not* read from ``flags.on_chain``, which a mid-anchor crash can leave set with
    no row.
    """
    return {
        "serial": card.serial,
        "cardId": card_id(card.serial),
        "name": card.name,
        "level": card.level,
        "rarity": card.rarity,
        "type": card.type,
        "shiny": card.shiny,
        "mintDate": _mint_date_iso(card),
        "thumbUrl": thumb_url(card.serial),
        "onChain": chain is not None,
    }


def card_detail(
    card: Card, *, day_number: int | None = None, chain: ChainAnchor | None = None
) -> dict[str, Any]:
    """Project a card onto the full ``Card`` schema plus derived display fields.

    ``dayNumber`` defaults to the serial: a card is the *n*-th slime to bloom and
    the serial is exactly that sequence number (``contracts/card.schema.json``).
    ``chain`` is populated from the decoded ``part = 8`` anchor row when one exists,
    and ``null`` otherwise; ``onChain`` is the boolean mirror of it (D1/D2). Both are
    driven by the anchor row — the evidence — never by ``flags.on_chain`` alone.
    """
    payload: dict[str, Any] = {
        "serial": card.serial,
        "cardId": card_id(card.serial),
        "name": card.name,
        "level": card.level,
        "rarity": card.rarity,
        "type": card.type,
        "shiny": card.shiny,
        "height_mm": card.height_mm,
        "weight_g": card.weight_g,
        "strength": card.strength,
        "endurance": card.endurance,
        "agility": card.agility,
        "happiness": card.happiness,
        "personality": card.personality,
        "power_name": card.power_name,
        "power_desc": card.power_desc,
        "quote": card.quote,
        "mintDate": _mint_date_iso(card),
        "dayNumber": card.serial if day_number is None else day_number,
        "imageUrl": image_url(card.serial),
        "thumbUrl": thumb_url(card.serial),
        "chain": chain_api_dict(chain) if chain is not None else None,
        "onChain": chain is not None,
    }
    house = contracts.rarity_houses().get(card.rarity)
    if house is not None:
        payload["rarityHouse"] = house
    palette = contracts.palette_for(card.type, card.rarity)
    if palette:
        payload["palette"] = palette
    payload["biome"] = contracts.biome_name(card.biome_id)
    payload["mood"] = contracts.mood_name(card.mood_id)
    payload["companion"] = (
        contracts.companion_name(card.companion_id) if card.flags.has_companion else None
    )
    return payload


def raw_view(card: Card, *, chain: ChainAnchor | None = None) -> dict[str, Any]:
    """Build the provenance view: the asmDB rows verbatim plus their decoding.

    Integers are rendered as strings exactly as asmDB returns them (a u64 does not
    survive a JS ``number``), the keccak256 ``cardHash`` is ``0x``-prefixed, and
    the decoded card is included so the "see the 175 bytes" panel can show the
    payload next to what it means. ``chain`` is threaded into the decoded card so
    its ``onChain``/``chain`` match the detail route (the anchor row is part 8, not
    part of the 175-byte header stream shown here).
    """
    rows = encode(card)
    stream = encode_stream(card)
    return {
        "rows": [
            {"id": str(row.id), "value": str(row.value), "tag": row.tag, "content": row.content}
            for row in rows
        ],
        "streamBytes": len(stream),
        "rowCount": len(rows),
        "cardHash": "0x" + card_hash(card).hex(),
        "decoded": card_detail(card, chain=chain),
    }


def nft_metadata(card: Card, *, base_url: str) -> dict[str, Any]:
    """Build the ERC-721 metadata document for a card.

    ``image`` is an absolute URL to the proxied PNG so wallets and marketplaces can
    fetch it; numeric traits use ``display_type: number`` and the mint date uses
    ``display_type: date`` with a Unix timestamp, per the ERC-721 metadata
    conventions.
    """
    serial = card.serial
    day = mint_date(card.mint_day)
    minted_at = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
    base = base_url if base_url.endswith("/") else base_url + "/"

    attributes: list[dict[str, Any]] = [
        {"trait_type": "Rarity", "value": card.rarity},
        {"trait_type": "Type", "value": card.type},
        {"trait_type": "Level", "value": card.level, "display_type": "number"},
        {"trait_type": "Strength", "value": card.strength, "display_type": "number"},
        {"trait_type": "Endurance", "value": card.endurance, "display_type": "number"},
        {"trait_type": "Agility", "value": card.agility, "display_type": "number"},
        {"trait_type": "Happiness", "value": card.happiness, "display_type": "number"},
        {"trait_type": "Height (mm)", "value": card.height_mm, "display_type": "number"},
        {"trait_type": "Weight (g)", "value": card.weight_g, "display_type": "number"},
        {"trait_type": "Shiny", "value": "Yes" if card.shiny else "No"},
        {"trait_type": "Mint Date", "value": minted_at, "display_type": "date"},
        {"trait_type": "Serial", "value": serial, "display_type": "number"},
    ]
    house = contracts.rarity_houses().get(card.rarity)
    if house is not None:
        attributes.insert(1, {"trait_type": "Rarity House", "value": house})

    return {
        "name": f"{card.name} ({card_id(serial)})",
        "description": (
            f"{card.personality} A {card.rarity} {card.type} PixelSlime that bloomed on "
            f"{day.isoformat()}. \u201c{card.quote}\u201d"
        ),
        "image": f"{base}api/cards/{serial}/image",
        "external_url": f"{base}",
        "attributes": attributes,
    }
