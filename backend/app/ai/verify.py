"""Step 4 of the pipeline: verification — does the picture match the JSON?

Three independent checks, because a card can fail in three unrelated ways:

* **Technical (Pillow, offline):** exactly 1024x1536, portrait, an alpha channel
  is present, and the four corners are genuinely transparent. A model that
  quietly paints an opaque backdrop is caught here.
* **Vision (gpt-5.6-sol, multimodal):** the printed name, level, rarity, type and
  four stats are read back off the image and compared to the source JSON.
* **Similarity guard:** the owner requires the slime's form to be *random and
  different* from Mochibo. A card that comes back as a pink dome slime in a cosy
  reading room with a cat is too close to the reference and is rejected. The
  semantic signal comes from the vision model; a deterministic average-hash of
  the art window is a cheap offline backstop.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
from PIL import Image

from ._chat import json_schema_format, request_structured
from .config import (
    CARD_HEIGHT,
    CARD_WIDTH,
    SIMILARITY_HASH_THRESHOLD,
    TEXT_MODEL,
)
from .errors import VerificationError

#: Corner pixels above this alpha (0..255) are treated as "not transparent".
_ALPHA_TRANSPARENT_MAX = 8


@dataclass(frozen=True, slots=True)
class TechnicalReport:
    """Result of the offline Pillow checks."""

    width: int
    height: int
    has_alpha: bool
    corner_alphas: tuple[int, int, int, int]
    corners_transparent: bool
    is_portrait: bool
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass(frozen=True, slots=True)
class VisionReport:
    """What the multimodal model read back off the rendered card."""

    matches: bool
    too_similar_to_reference: bool
    mismatches: list[str]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Aggregate verdict for one rendered card."""

    ok: bool
    reasons: list[str]
    technical: TechnicalReport
    similarity_score: float
    vision: VisionReport | None


def _open_rgba(png_bytes: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
    except Exception as exc:
        raise VerificationError(f"could not open rendered image: {exc}") from exc
    return img


def check_technical(png_bytes: bytes) -> TechnicalReport:
    """Run the offline dimensional/alpha checks on the rendered PNG."""
    img = _open_rgba(png_bytes)
    width, height = img.size
    has_alpha = "A" in img.getbands()
    failures: list[str] = []

    if (width, height) != (CARD_WIDTH, CARD_HEIGHT):
        failures.append(f"dimensions are {width}x{height}, expected {CARD_WIDTH}x{CARD_HEIGHT}")
    is_portrait = height > width
    if not is_portrait:
        failures.append(f"image is not portrait ({width}x{height})")

    if has_alpha:
        alpha = img.getchannel("A")
        corners = (
            alpha.getpixel((0, 0)),
            alpha.getpixel((width - 1, 0)),
            alpha.getpixel((0, height - 1)),
            alpha.getpixel((width - 1, height - 1)),
        )
        corner_alphas = tuple(int(cast("float", c)) for c in corners)
    else:
        failures.append("image has no alpha channel")
        corner_alphas = (255, 255, 255, 255)

    corners_transparent = all(a <= _ALPHA_TRANSPARENT_MAX for a in corner_alphas)
    if not corners_transparent:
        failures.append(f"the four corners are not transparent (alphas={corner_alphas})")

    return TechnicalReport(
        width=width,
        height=height,
        has_alpha=has_alpha,
        corner_alphas=corner_alphas,  # type: ignore[arg-type]
        corners_transparent=corners_transparent,
        is_portrait=is_portrait,
        failures=failures,
    )


def _art_window(img: Image.Image) -> Image.Image:
    """Crop the central art window — where the creature/scene live.

    The similarity guard compares only this region, not the whole card: every
    card shares Mochibo's *layout* by design, so a full-card hash would be high
    for all of them. The art window is what must actually differ.
    """
    width, height = img.size
    left, right = int(0.10 * width), int(0.90 * width)
    top, bottom = int(0.22 * height), int(0.62 * height)
    return img.crop((left, top, right, bottom))


def average_hash(img: Image.Image, *, size: int = 8) -> int:
    """Classic average-hash: mean-threshold an ``size x size`` grayscale."""
    small = img.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = cast("list[int]", small.get_flattened_data())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, pixel in enumerate(pixels):
        if pixel >= avg:
            bits |= 1 << i
    return bits


def hash_agreement(a: int, b: int, *, size: int = 8) -> float:
    """Fraction of matching bits between two average hashes (1.0 == identical)."""
    total = size * size
    hamming = bin(a ^ b).count("1")
    return (total - hamming) / total


def check_similarity(png_bytes: bytes, reference_bytes: bytes) -> float:
    """Return art-window average-hash agreement between a card and the reference."""
    card_hash = average_hash(_art_window(_open_rgba(png_bytes)))
    ref_hash = average_hash(_art_window(_open_rgba(reference_bytes)))
    return hash_agreement(card_hash, ref_hash)


def _vision_schema() -> dict[str, Any]:
    integer = {"type": "integer"}
    string = {"type": "string"}
    boolean = {"type": "boolean"}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "printed_name": string,
            "printed_level": integer,
            "printed_rarity": string,
            "printed_type": string,
            "printed_strength": integer,
            "printed_endurance": integer,
            "printed_agility": integer,
            "printed_happiness": integer,
            "background_transparent": boolean,
            "is_pink_dome_slime": boolean,
            "scene_is_cozy_reading_room": boolean,
            "has_cat_companion": boolean,
        },
        "required": [
            "printed_name",
            "printed_level",
            "printed_rarity",
            "printed_type",
            "printed_strength",
            "printed_endurance",
            "printed_agility",
            "printed_happiness",
            "background_transparent",
            "is_pink_dome_slime",
            "scene_is_cozy_reading_room",
            "has_cat_companion",
        ],
    }


def _data_uri(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _compare_vision(card: Mapping[str, Any], read: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []

    def norm(value: Any) -> str:
        return str(value).strip().casefold()

    if norm(read.get("printed_name")) != norm(card["name"]):
        mismatches.append(f"name: printed {read.get('printed_name')!r} != {card['name']!r}")
    if norm(read.get("printed_rarity")) != norm(card["rarity"]):
        mismatches.append(f"rarity: printed {read.get('printed_rarity')!r} != {card['rarity']!r}")
    if norm(read.get("printed_type")) != norm(card["type"]):
        mismatches.append(f"type: printed {read.get('printed_type')!r} != {card['type']!r}")
    for field_name, printed_key in (
        ("level", "printed_level"),
        ("strength", "printed_strength"),
        ("endurance", "printed_endurance"),
        ("agility", "printed_agility"),
        ("happiness", "printed_happiness"),
    ):
        if read.get(printed_key) != card[field_name]:
            mismatches.append(
                f"{field_name}: printed {read.get(printed_key)!r} != {card[field_name]!r}"
            )
    return mismatches


async def check_vision(
    png_bytes: bytes,
    card: Mapping[str, Any],
    *,
    client: httpx.AsyncClient,
) -> VisionReport:
    """Read the card back with the multimodal model and compare to the JSON."""
    body = {
        "model": TEXT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict QA checker for collectible trading cards. Read "
                    "ONLY what is actually printed on the card image and report it. "
                    "Output only the requested JSON."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Read the printed NAME, LEVEL, RARITY, TYPE and the four "
                            "stats (STRENGTH, ENDURANCE, AGILITY, HAPPINESS). Also judge: "
                            "is the area outside the card border transparent; is the "
                            "creature a pink dome-shaped slime; is the scene a cosy "
                            "reading room; is there a cat companion."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": _data_uri(png_bytes)}},
                ],
            },
        ],
        "response_format": json_schema_format("pixelslime_card_readback", _vision_schema()),
    }
    content = await request_structured(client, body, error_cls=VerificationError)
    try:
        read: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"vision model returned non-JSON: {exc}") from exc

    mismatches = _compare_vision(card, read)
    mochibo_signals = sum(
        bool(read.get(key))
        for key in ("is_pink_dome_slime", "scene_is_cozy_reading_room", "has_cat_companion")
    )
    too_similar = mochibo_signals >= 2
    return VisionReport(
        matches=not mismatches,
        too_similar_to_reference=too_similar,
        mismatches=mismatches,
        raw=read,
    )


async def verify_card(
    png_bytes: bytes,
    card: Mapping[str, Any],
    *,
    client: httpx.AsyncClient,
    reference_bytes: bytes,
    run_vision: bool = True,
) -> VerificationResult:
    """Aggregate the technical, similarity and vision checks into one verdict.

    Returns a result (it does not raise on a soft mismatch) so the orchestrator
    can regenerate the image once before alerting, per ``docs/PLAN.md`` §5.
    """
    reasons: list[str] = []

    technical = check_technical(png_bytes)
    reasons.extend(technical.failures)

    similarity_score = check_similarity(png_bytes, reference_bytes)
    if similarity_score >= SIMILARITY_HASH_THRESHOLD:
        reasons.append(
            f"art window is too similar to the reference (hash agreement "
            f"{similarity_score:.2f} >= {SIMILARITY_HASH_THRESHOLD})"
        )

    vision: VisionReport | None = None
    if run_vision:
        vision = await check_vision(png_bytes, card, client=client)
        reasons.extend(vision.mismatches)
        if vision.too_similar_to_reference:
            reasons.append("vision check: card resembles Mochibo (pink dome slime / room / cat)")

    return VerificationResult(
        ok=not reasons,
        reasons=reasons,
        technical=technical,
        similarity_score=similarity_score,
        vision=vision,
    )
