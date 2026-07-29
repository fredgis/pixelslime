"""Shared, network-free helpers for the W4 AI pipeline tests.

Kept as a flat module (imported by name, like ``tests/codec/_helpers.py``) so the
image factories, cassette loader and response envelopes can be reused across the
test modules without going through fixtures where a plain function reads better.

No real PNG larger than a few hundred bytes is ever committed: ``make_card_png``
synthesises tiny-but-real RGBA canvases at the true card dimensions, so the Pillow
checks run against genuine images without a megabyte fixture.
"""

from __future__ import annotations

import base64
import io
import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.ai.config import CARD_HEIGHT, CARD_WIDTH
from app.ai.models import Card

_CASSETTES = Path(__file__).resolve().parent / "cassettes"


def _encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _art_noise(width: int, height: int, seed: int) -> tuple[Image.Image, tuple[int, int]]:
    """Build a seeded RGBA noise patch sized to the central art window."""
    rnd = random.Random(seed)
    small = Image.new("RGB", (8, 8))
    small.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(64)])
    left, right = int(0.10 * width), int(0.90 * width)
    top, bottom = int(0.22 * height), int(0.62 * height)
    patch = small.resize((right - left, bottom - top), Image.Resampling.NEAREST).convert("RGBA")
    return patch, (left, top)


def make_card_png(
    *,
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
    opaque: bool = False,
    with_alpha: bool = True,
    seed: int = 0,
) -> bytes:
    """Synthesise a tiny-but-real card PNG.

    Defaults produce a valid card canvas: correct dimensions, an alpha channel,
    fully transparent corners and seeded noise in the art window (so two seeds
    hash differently). ``opaque`` paints every pixel solid (corners fail the
    transparency check); ``with_alpha=False`` yields an RGB image with no alpha
    channel at all.
    """
    if not with_alpha:
        return _encode_png(Image.new("RGB", (width, height), (180, 200, 220)))
    if opaque:
        return _encode_png(Image.new("RGBA", (width, height), (200, 180, 160, 255)))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    patch, origin = _art_noise(width, height, seed)
    img.paste(patch, origin)
    return _encode_png(img)


def tiny_png() -> bytes:
    """A minimal 4x4 opaque PNG, for base64 decode round-trips."""
    return _encode_png(Image.new("RGBA", (4, 4), (10, 20, 30, 255)))


def make_white_bordered_png(
    *,
    width: int = CARD_WIDTH,
    height: int = CARD_HEIGHT,
    interior_island: bool = True,
) -> bytes:
    """A solid-white canvas with a dark centred 'card' rectangle.

    Mimics what gpt-image-2 actually returns from ``/images/edits``: an opaque
    flat-white exterior around the card (it cannot emit alpha). ``interior_island``
    paints a white patch *inside* the dark card so a corner flood-fill test can
    prove enclosed whites are left opaque.
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    margin = max(2, width // 10)
    draw.rectangle(
        (margin, margin, width - margin - 1, height - margin - 1), fill=(40, 30, 20, 255)
    )
    if interior_island:
        cx, cy = width // 2, height // 2
        r = max(1, width // 12)
        draw.rectangle((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    return _encode_png(img)


def image_edits_response(png_bytes: bytes) -> dict[str, Any]:
    """The ``/images/edits`` success envelope wrapping ``png_bytes``."""
    return {"data": [{"b64_json": base64.b64encode(png_bytes).decode("ascii")}]}


def chat_response(content: dict[str, Any], *, finish_reason: str = "stop") -> dict[str, Any]:
    """A ``/chat/completions`` envelope whose message content is ``content`` as JSON."""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": json.dumps(content)},
                "finish_reason": finish_reason,
            }
        ]
    }


def metadata_payload(**overrides: Any) -> dict[str, Any]:
    """A valid set of the twelve model-written metadata fields."""
    payload: dict[str, Any] = {
        "name": "Pebblory",
        "level": 12,
        "height_mm": 240,
        "weight_g": 800,
        "strength": 41,
        "endurance": 55,
        "agility": 63,
        "happiness": 88,
        "personality": "A shy pebble slime who hums to itself while tidying tiny stones.",
        "power_name": "Stone Lullaby",
        "power_desc": "Sings nearby rocks to sleep so they stack themselves into a wall.",
        "quote": "Let's build something cosy.",
    }
    payload.update(overrides)
    return payload


def vision_payload(card: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """A vision-readback payload that agrees with ``card`` unless overridden."""
    payload: dict[str, Any] = {
        "printed_name": card["name"],
        "printed_level": card["level"],
        "printed_rarity": card["rarity"],
        "printed_type": card["type"],
        "printed_strength": card["strength"],
        "printed_endurance": card["endurance"],
        "printed_agility": card["agility"],
        "printed_happiness": card["happiness"],
        "background_transparent": True,
        "is_pink_dome_slime": False,
        "scene_is_cozy_reading_room": False,
        "has_cat_companion": False,
    }
    payload.update(overrides)
    return payload


def valid_card_dict(**overrides: Any) -> dict[str, Any]:
    """Return a schema-valid card dict, assembled through the ``Card`` model."""
    base: dict[str, Any] = {
        "series": "PS",
        "serial": 1,
        "name": "Pebblory",
        "level": 12,
        "rarity": "COMMON",
        "type": "STONE",
        "height_mm": 240,
        "weight_g": 800,
        "strength": 41,
        "endurance": 55,
        "agility": 63,
        "happiness": 88,
        "art_id": 17,
        "style_id": 1,
        "frame_id": 0,
        "background_id": 42,
        "biome_id": 0,
        "mood_id": 6,
        "personality": "A shy pebble slime who hums to itself while tidying tiny stones.",
        "power_name": "Stone Lullaby",
        "power_desc": "Sings nearby rocks to sleep so they stack themselves into a wall.",
        "quote": "Let's build something cosy.",
        "mint_day": 200,
        "shiny": False,
        "flags": {"has_companion": False, "has_accessory": True},
        "biome": "Open Meadow",
    }
    base.update(overrides)
    return Card.model_validate(base).model_dump(by_alias=True, exclude_none=True)


def load_cassette(name: str) -> dict[str, Any]:
    """Load a recorded response envelope from ``tests/ai/cassettes``."""
    data: dict[str, Any] = json.loads((_CASSETTES / name).read_text(encoding="utf-8"))
    return data


def cassette_exists(name: str) -> bool:
    return (_CASSETTES / name).is_file()
