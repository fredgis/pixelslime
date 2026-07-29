"""Static configuration and contract-derived constants for the AI pipeline.

Everything the pipeline needs to know that is *not* rolled or written by a model
lives here: the verified endpoint facts (``docs/PLAN.md`` §1.1), the codec text
limits (``docs/CODEC.md`` §3.6), and the curated creative tables (biomes, moods,
companions) that turn a reproducible roll into a scene.

Rarity weights and the 16 types are **loaded from the contracts**, never
duplicated, so W0 stays the single source of truth (``docs/AGENTS.md``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final, cast

# ── The verified image/text endpoint (docs/PLAN.md §1.1) ────────────────────
#: OpenAI-compatible ``/v1`` surface on the ``fgi`` Azure AI Foundry resource.
API_BASE_URL: Final = "https://fgi.services.ai.azure.com/openai/v1/"
#: Entra scope for ``DefaultAzureCredential``. API-key auth is disabled.
TOKEN_SCOPE: Final = "https://cognitiveservices.azure.com/.default"  # noqa: S105  # OAuth scope, not a secret
#: Deployment names (confirmed live on the ``fgi`` account).
IMAGE_MODEL: Final = "gpt-image-2"
TEXT_MODEL: Final = "gpt-5.6-sol"

# ── Image request parameters (all verified accepted) ────────────────────────
CARD_WIDTH: Final = 1024
CARD_HEIGHT: Final = 1536
CARD_SIZE: Final = f"{CARD_WIDTH}x{CARD_HEIGHT}"  # both divisible by 16
# gpt-image-2 on /images/edits CANNOT emit alpha: background="transparent" is
# rejected (HTTP 400 "Transparent background is not supported for this model")
# and background="auto" returns an opaque RGB render. docs/PLAN.md §1.1 verified
# transparency on /images/generations and *assumed* it held for /edits — it does
# not (see the W4 report). So we render opaque with a flat white exterior and
# recover real alpha in Pillow (imagegen.background_to_alpha) — this keeps the
# §5.2 reference strategy while still satisfying the hard transparency rule.
IMAGE_BACKGROUND: Final = "auto"
#: Flood-fill tolerance (summed RGBA channel distance, 0..1020) for keying the
#: flat exterior to transparency. 50 cleanly keys a pure-white margin against the
#: dark card frame without nibbling the frame edge.
IMAGE_BG_KEY_THRESHOLD: Final = 50
#: A keyed card's exterior margin is ~13% of the frame; if flood-fill removes
#: more than this fraction it has leaked into the card, so we reject the render.
IMAGE_BG_KEY_MAX_FRACTION: Final = 0.75
IMAGE_OUTPUT_FORMAT: Final = "png"
IMAGE_QUALITY: Final = "high"
THUMB_WIDTH: Final = 512
THUMB_HEIGHT: Final = 768

#: gpt-image-2 rate limit is 2 requests / 60 s. Used to space real calls.
IMAGE_MIN_SPACING_SECONDS: Final = 35

# ── Text length limits, normative from docs/CODEC.md §3.6 ────────────────────
# Enforced at encode time; exceeding any of them is an error, never a
# truncation. Both the character count and the UTF-8 byte count must hold.
TEXT_CHAR_LIMITS: Final[dict[str, int]] = {
    "name": 18,
    "personality": 90,
    "power_name": 20,
    "power_desc": 90,
    "quote": 40,
}
TEXT_BYTE_LIMITS: Final[dict[str, int]] = {
    "name": 36,
    "personality": 180,
    "power_name": 40,
    "power_desc": 180,
    "quote": 80,
}
#: None of the five text fields may contain any of these (docs/CODEC.md §3.6).
FORBIDDEN_TEXT_CHARS: Final = ("\x1f", "\x00", "\r", "\n")

# ── Numeric ranges, mirrored from contracts/card.schema.json ────────────────
LEVEL_RANGE: Final = (1, 100)
HEIGHT_MM_RANGE: Final = (1, 65535)
WEIGHT_G_RANGE: Final = (1, 65535)
STAT_RANGE: Final = (0, 100)

# ── Rarity ordering (docs/PLAN.md §2.4). Ordinal == frame_id convention. ─────
RARITY_ORDER: Final[tuple[str, ...]] = (
    "COMMON",
    "UNCOMMON",
    "RARE",
    "EPIC",
    "LEGENDARY",
    "MYTHIC",
)
#: The pity timer forces a roll to at least this tier. See docs/PLAN.md §2.4.
PITY_FLOOR_RARITY: Final = "RARE"
PITY_WINDOW_DAYS: Final = 14

#: A card is "≥ RARE" from this ordinal up.
RARE_ORDINAL: Final = RARITY_ORDER.index(PITY_FLOOR_RARITY)

# ── Per-tier finish, spelled out for the image prompt (docs/PLAN.md §5.1) ────
# The *anatomy* is pinned by the reference image; the *finish* is pinned by
# these words. Keeping COMMON deliberately humble is the whole reason the
# rarity split exists (docs/PLAN.md §5.2, risk R12).
RARITY_FINISHES: Final[dict[str, str]] = {
    "COMMON": (
        "a plain, sturdy WOODEN frame with a soft, muted palette. No gold, no "
        "gems, no foil, no glow, no sparkle particles. Keep it humble, simple "
        "and clearly the least ornate tier."
    ),
    "UNCOMMON": (
        "a brushed SILVER frame with a faint light halo. A slightly brighter "
        "palette than common. Minimal ornamentation, no gold, no gems."
    ),
    "RARE": (
        "a polished BLUE frame with cool prismatic highlights and gentle light "
        "refractions. A richer palette. No gold and no crown gem."
    ),
    "EPIC": (
        "an ornate GOLD-AND-VIOLET frame with a crown gem and sparkle. A rich, "
        "jewel-like palette. This is the ornate tier."
    ),
    "LEGENDARY": (
        "a celestial frame that looks animated, set over a constellation "
        "backdrop, with a luminous palette and glowing particles. More "
        "exceptional and radiant than epic."
    ),
    "MYTHIC": (
        "iridescent RAINBOW FOIL on a frame that overflows its own bounds, the "
        "most exceptional palette of all, with maximal glow and drifting "
        "particles. The rarest, most spectacular finish."
    ),
}

#: All cards share one pixel-art style version; bumped only if the style changes.
STYLE_ID: Final = 1

# ── Curated creative tables (W4-owned; not yet in contracts) ────────────────
# biome_id / mood_id are the *list index* here, which is what the card carries
# (card.schema.json: 0..255). The display strings resolve client-side; until a
# shared table exists in contracts/, this package is the source of that mapping.
BIOMES: Final[tuple[str, ...]] = (
    "Open Meadow",
    "Sunlit Forest",
    "Tide Pool Cove",
    "Cozy Bedroom",
    "Cozy Reading Room",
    "Rainy Street",
    "Cluttered Workshop",
    "Library at Dusk",
    "Mushroom Grove",
    "Snowy Village",
    "Candy Kitchen",
    "Starlit Rooftop",
    "Rockpool Cavern",
    "Sunny Greenhouse",
    "Arcade Corner",
    "Cloud Terrace",
)
MOODS: Final[tuple[str, ...]] = (
    "Cheerful",
    "Sleepy",
    "Curious",
    "Mischievous",
    "Serene",
    "Excited",
    "Bashful",
    "Determined",
    "Dreamy",
    "Grumpy",
)
COMPANIONS: Final[tuple[str, ...]] = (
    "Sleepy Puff Cat",
    "Tiny Sparrow",
    "Bumble Bee Buddy",
    "Pebble Crab",
    "Glow Moth",
    "Acorn Squirrel",
    "Paper Crane",
    "Bubble Fish",
    "Clover Bunny",
    "Ember Pup",
    "Frost Fawn",
    "Star Tadpole",
)
ACCESSORIES: Final[tuple[str, ...]] = (
    "a tiny wizard hat",
    "round spectacles",
    "a flower crown",
    "a knitted scarf",
    "a little backpack",
    "a bell collar",
    "a leaf umbrella",
    "star hairpins",
    "a polka-dot bow tie",
    "cozy mittens",
)

#: Probabilities for the boolean/optional draws. Not in contracts — W4's call.
P_COMPANION: Final = 0.45
P_ACCESSORY: Final = 0.40
P_SHINY: Final = 0.03

#: How close (0..1 average-hash agreement) a card may be to Mochibo before the
#: similarity guard rejects it. 1.0 == identical hash. See verify.py.
SIMILARITY_HASH_THRESHOLD: Final = 0.82


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the repository root by walking up until ``contracts/`` is found.

    Robust to being imported from an installed wheel or the source tree; we do
    not hard-code a parent depth so a move of this file cannot silently break
    contract loading.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "contracts" / "card.schema.json").is_file():
            return parent
    raise FileNotFoundError(
        f"could not locate the repository root (no contracts/card.schema.json above {here})"
    )


def contracts_dir() -> Path:
    return repo_root() / "contracts"


def assets_template_dir() -> Path:
    return repo_root() / "assets" / "template"


@lru_cache(maxsize=1)
def _design_tokens() -> dict[str, object]:
    path = contracts_dir() / "design-tokens.json"
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _card_schema() -> dict[str, object]:
    path = contracts_dir() / "card.schema.json"
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def rarity_weights() -> dict[str, float]:
    """Return ``{rarity: weight}`` loaded from ``contracts/design-tokens.json``.

    We read the weights from the contract rather than restating them so the
    distribution can only ever be changed in one place (W0).
    """
    tokens = _design_tokens()
    rarity = tokens["rarity"]
    assert isinstance(rarity, dict)
    weights: dict[str, float] = {}
    for name in RARITY_ORDER:
        entry = rarity[name]
        assert isinstance(entry, dict)
        weights[name] = float(entry["weight"])
    return weights


@lru_cache(maxsize=1)
def card_types() -> tuple[str, ...]:
    """Return the 16 card types in the canonical order of the card schema."""
    schema = _card_schema()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    type_prop = properties["type"]
    assert isinstance(type_prop, dict)
    enum = type_prop["enum"]
    assert isinstance(enum, list)
    return tuple(str(t) for t in enum)


def rarity_ordinal(rarity: str) -> int:
    """Map a rarity name to its ordinal (COMMON=0 … MYTHIC=5)."""
    return RARITY_ORDER.index(rarity)
