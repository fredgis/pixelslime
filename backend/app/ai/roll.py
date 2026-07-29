"""Step 1 of the pipeline: the roll — reproducible, in code, never the model.

``docs/PLAN.md`` §2.4 is emphatic that the rarity roll happens here, not in the
LLM: *"that is the only way to get a genuinely controlled and auditable
distribution."* This module also draws the type, biome, mood, companion,
accessory and shiny flag, and every draw is derived from a seed computed from the
mint date, so re-running a given day reproduces the same card exactly.

The rarity weights come from ``contracts/design-tokens.json`` (via
``config.rarity_weights``); they are never restated here.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

from .config import (
    ACCESSORIES,
    BIOMES,
    COMPANIONS,
    MOODS,
    P_ACCESSORY,
    P_COMPANION,
    P_SHINY,
    PITY_WINDOW_DAYS,
    RARE_ORDINAL,
    RARITY_ORDER,
    card_types,
    rarity_ordinal,
    rarity_weights,
)
from .errors import RollError


@dataclass(frozen=True, slots=True)
class MintedCard:
    """A minimal record of an already-minted card, for the pity timer."""

    mint_day: int
    rarity: str


@dataclass(frozen=True, slots=True)
class Roll:
    """The fully-resolved, reproducible outcome of step 1.

    ``card_type`` (not ``type``) avoids shadowing the builtin; it maps to the
    card's ``type`` field downstream. ``biome_id`` / ``mood_id`` are the list
    indices carried by the card; the display strings are resolved here.
    """

    mint_day: int
    seed: int
    rarity: str
    card_type: str
    biome_id: int
    biome: str
    mood_id: int
    mood: str
    has_companion: bool
    companion: str | None
    has_accessory: bool
    accessory: str | None
    shiny: bool
    art_id: int
    background_id: int
    pity_forced: bool

    @property
    def rarity_ordinal(self) -> int:
        return rarity_ordinal(self.rarity)


def derive_seed(mint_day: int) -> int:
    """Derive a stable 64-bit seed from the mint day.

    We hash rather than seed the RNG with ``mint_day`` directly so consecutive
    days do not produce correlated first draws, and we use SHA-256 rather than
    ``hash()`` so the seed is identical across processes and Python versions —
    reproducibility is the whole point.
    """
    digest = hashlib.sha256(f"pixelslime/roll/v1/{mint_day}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _weight_list() -> list[float]:
    weights = rarity_weights()
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise RollError(f"rarity weights must sum to 1.0, got {total}")
    return [weights[name] for name in RARITY_ORDER]


def weighted_rarity(rng: random.Random) -> str:
    """Draw one rarity from the full weighted distribution.

    Exposed on its own so the distribution can be validated over a large sample
    without the pity timer or the rest of the roll getting in the way.
    """
    return rng.choices(RARITY_ORDER, weights=_weight_list(), k=1)[0]


def _rarity_at_least(rng: random.Random, floor_ordinal: int) -> str:
    """Draw a rarity restricted to tiers ``>= floor_ordinal`` (conditional).

    Used by the pity timer: the guaranteed card is still drawn from the real
    conditional distribution, so a forced RARE is usually RARE and only rarely a
    MYTHIC — the odds simply renormalise over the eligible tiers.
    """
    population = list(RARITY_ORDER[floor_ordinal:])
    weights = _weight_list()[floor_ordinal:]
    return rng.choices(population, weights=weights, k=1)[0]


def pity_active(mint_day: int, history: Sequence[MintedCard]) -> bool:
    """Return whether the anti-frustration pity timer must force a high roll.

    Rule (``docs/PLAN.md`` §2.4): if the 14 days immediately before ``mint_day``
    are fully covered by minted cards and none of them is ≥ RARE, force ≥ RARE.
    We require the window to be *full* (14 cards, given the one-card-per-day
    invariant) so a brand-new collection is not forced into a rare on day 3.
    """
    window = [card for card in history if mint_day - PITY_WINDOW_DAYS <= card.mint_day < mint_day]
    if len(window) < PITY_WINDOW_DAYS:
        return False
    return not any(rarity_ordinal(card.rarity) >= RARE_ORDINAL for card in window)


def roll(
    mint_day: int,
    history: Sequence[MintedCard] = (),
    *,
    forced_rarity: str | None = None,
) -> Roll:
    """Produce the reproducible roll for ``mint_day``.

    ``forced_rarity`` pins the tier (used to hand-seed the reference exemplars,
    e.g. the first COMMON and LEGENDARY); the natural draw is still consumed so
    the remaining draws are unaffected by the override. The pity timer only ever
    applies to a natural roll.
    """
    if forced_rarity is not None and forced_rarity not in RARITY_ORDER:
        raise RollError(f"unknown forced_rarity {forced_rarity!r}")

    seed = derive_seed(mint_day)
    rng = random.Random(seed)  # noqa: S311  # deterministic, non-crypto by design

    natural = weighted_rarity(rng)
    forced_by_pity = False
    if forced_rarity is not None:
        rarity = forced_rarity
    else:
        rarity = natural
        if pity_active(mint_day, history) and rarity_ordinal(rarity) < RARE_ORDINAL:
            rarity = _rarity_at_least(rng, RARE_ORDINAL)
            forced_by_pity = True

    card_type = rng.choice(card_types())

    biome_id = rng.randrange(len(BIOMES))
    mood_id = rng.randrange(len(MOODS))

    has_companion = rng.random() < P_COMPANION
    companion = rng.choice(COMPANIONS) if has_companion else None

    has_accessory = rng.random() < P_ACCESSORY
    accessory = rng.choice(ACCESSORIES) if has_accessory else None

    shiny = rng.random() < P_SHINY

    art_id = rng.randrange(256)
    background_id = rng.randrange(256)

    return Roll(
        mint_day=mint_day,
        seed=seed,
        rarity=rarity,
        card_type=card_type,
        biome_id=biome_id,
        biome=BIOMES[biome_id],
        mood_id=mood_id,
        mood=MOODS[mood_id],
        has_companion=has_companion,
        companion=companion,
        has_accessory=has_accessory,
        accessory=accessory,
        shiny=shiny,
        art_id=art_id,
        background_id=background_id,
        pity_forced=forced_by_pity,
    )
