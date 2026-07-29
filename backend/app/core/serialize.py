"""Pure card → JSON projections for the API layer.

The router modules stay thin by delegating every shape in ``contracts/openapi.yaml``
to a function here: the gallery :func:`card_summary`, the full :func:`card_detail`,
the ERC-721 :func:`nft_metadata`, and the provenance :func:`raw_view`. None of
these touch the network — even ``raw_view`` re-derives the asmDB rows by *re-encoding*
the decoded card through the real codec, which is byte-identical to what asmDB
stores (the codec is deterministic) and so needs no round-trip.

Two schema fields are resolved from W4's frozen lookup tables
(``contracts/lookups.json``): ``biome`` from ``biome_id`` and ``companion`` from
``companion_id`` (only when ``flags.has_companion`` is set). ``mood`` is resolved
from ``mood_id`` too; note it is not (yet) declared in the OpenAPI ``Card`` schema
— see the W7 report. Ids out of range degrade to an omitted field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.codec import Card, card_hash, encode, encode_stream

from . import contracts
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


def card_summary(card: Card) -> dict[str, Any]:
    """Project a card onto ``CardSummary`` — what the gallery grid needs, no more."""
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
        "onChain": card.flags.on_chain,
    }


def card_detail(card: Card, *, day_number: int | None = None) -> dict[str, Any]:
    """Project a card onto the full ``Card`` schema plus derived display fields.

    ``dayNumber`` defaults to the serial: a card is the *n*-th slime to bloom and
    the serial is exactly that sequence number (``contracts/card.schema.json``).
    ``chain`` is ``null`` until the on-chain anchor (PSC-1 part 8) is decodable —
    see the W7 report — but ``on-chain`` status is still surfaced via the header
    flag.
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
        "chain": None,
    }
    house = contracts.rarity_houses().get(card.rarity)
    if house is not None:
        payload["rarityHouse"] = house
    palette = contracts.palette_for(card.type, card.rarity)
    if palette:
        payload["palette"] = palette
    biome = contracts.biome_name(card.biome_id)
    if biome is not None:
        payload["biome"] = biome
    mood = contracts.mood_name(card.mood_id)
    if mood is not None:
        payload["mood"] = mood
    if card.flags.has_companion:
        companion = contracts.companion_name(card.companion_id)
        if companion is not None:
            payload["companion"] = companion
    return payload


def raw_view(card: Card) -> dict[str, Any]:
    """Build the provenance view: the asmDB rows verbatim plus their decoding.

    Integers are rendered as strings exactly as asmDB returns them (a u64 does not
    survive a JS ``number``), the keccak256 ``cardHash`` is ``0x``-prefixed, and
    the decoded card is included so the "see the 175 bytes" panel can show the
    payload next to what it means.
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
        "decoded": card_detail(card),
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
