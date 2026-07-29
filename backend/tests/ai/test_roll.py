"""Tests for the in-code roll: distribution, pity timer and reproducibility."""

from __future__ import annotations

import math
import random

from app.ai.config import (
    P_ACCESSORY,
    P_COMPANION,
    RARE_ORDINAL,
    RARITY_ORDER,
    rarity_ordinal,
    rarity_weights,
)
from app.ai.roll import (
    MintedCard,
    derive_seed,
    pity_active,
    roll,
    weighted_rarity,
)

_N = 200_000
_SIGMA = 5.0  # 5-sigma band: a fixed-seed run never trips it, real drift does


def test_rarity_distribution_matches_weights_within_tolerance() -> None:
    rng = random.Random(0xC0FFEE)
    counts = dict.fromkeys(RARITY_ORDER, 0)
    for _ in range(_N):
        counts[weighted_rarity(rng)] += 1

    weights = rarity_weights()
    for rarity in RARITY_ORDER:
        p = weights[rarity]
        expected = _N * p
        sigma = math.sqrt(_N * p * (1.0 - p))
        observed = counts[rarity]
        assert abs(observed - expected) <= _SIGMA * sigma, (
            f"{rarity}: observed {observed} ({observed / _N:.5f}) vs expected "
            f"{expected:.1f} ({p:.5f}), off by {abs(observed - expected) / sigma:.2f} sigma"
        )


def test_boolean_draw_frequencies_are_close() -> None:
    rng = random.Random(1234)
    companions = sum(rng.random() < P_COMPANION for _ in range(_N))
    accessories = sum(rng.random() < P_ACCESSORY for _ in range(_N))
    assert abs(companions / _N - P_COMPANION) < 0.01
    assert abs(accessories / _N - P_ACCESSORY) < 0.01


def test_roll_is_reproducible_from_mint_day() -> None:
    a = roll(4242)
    b = roll(4242)
    assert a == b


def test_different_days_differ() -> None:
    seeds = {derive_seed(day) for day in range(50)}
    assert len(seeds) == 50  # no collisions across a run of days


def test_seed_is_stable_constant() -> None:
    # Pinning the derivation guards against an accidental change to the hash
    # recipe silently altering every historical card.
    assert derive_seed(0) == int.from_bytes(
        __import__("hashlib").sha256(b"pixelslime/roll/v1/0").digest()[:8], "big"
    )


def test_forced_rarity_overrides_but_consumes_natural_draw() -> None:
    forced = roll(100, forced_rarity="LEGENDARY")
    natural = roll(100)
    assert forced.rarity == "LEGENDARY"
    # Everything downstream of the rarity draw is identical: the natural draw is
    # still consumed so a forced card does not desync the rest of the roll.
    assert forced.card_type == natural.card_type
    assert forced.biome_id == natural.biome_id
    assert forced.mood_id == natural.mood_id
    assert forced.art_id == natural.art_id
    assert forced.pity_forced is False


def test_roll_fields_are_within_contract_ranges() -> None:
    r = roll(777)
    assert 0 <= r.art_id <= 255
    assert 0 <= r.background_id <= 255
    assert r.rarity in RARITY_ORDER
    assert (r.companion is None) == (not r.has_companion)
    assert (r.accessory is None) == (not r.has_accessory)


def _history(days: range, rarity: str) -> list[MintedCard]:
    return [MintedCard(mint_day=d, rarity=rarity) for d in days]


def test_pity_inactive_when_window_not_full() -> None:
    # Only 10 of the 14 preceding days are covered -> a new collection is not
    # dragged into a forced rare.
    history = _history(range(90, 100), "COMMON")
    assert pity_active(100, history) is False


def test_pity_active_when_full_window_all_below_rare() -> None:
    history = _history(range(86, 100), "COMMON")  # days 86..99 == 14 days
    assert pity_active(100, history) is True


def test_pity_inactive_when_window_contains_a_rare() -> None:
    history = [*_history(range(86, 99), "COMMON"), MintedCard(mint_day=99, rarity="RARE")]
    assert pity_active(100, history) is False


def test_pity_forces_at_least_rare_and_sets_flag() -> None:
    # Choose a day whose natural draw is below RARE, then prove the pity timer
    # lifts it to >= RARE and records that it did so.
    day = next(d for d in range(1, 5000) if rarity_ordinal(roll(d).rarity) < RARE_ORDINAL)
    history = _history(range(day - 14, day), "COMMON")
    forced = roll(day, history)
    assert rarity_ordinal(forced.rarity) >= RARE_ORDINAL
    assert forced.pity_forced is True


def test_pity_does_not_downgrade_a_natural_high_roll() -> None:
    day = next(d for d in range(1, 5000) if rarity_ordinal(roll(d).rarity) >= RARE_ORDINAL)
    history = _history(range(day - 14, day), "COMMON")
    forced = roll(day, history)
    assert rarity_ordinal(forced.rarity) >= RARE_ORDINAL
    assert forced.pity_forced is False  # it was already high; pity did not fire
