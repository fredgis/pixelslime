"""The $SMILE economy, mirrored from the deployed contracts.

Two numbers drive every economy display on the site, and both are *pure functions of
the cards* — no chain call is needed to show them:

``smile_yield(card)``
    What ``ClaimPool.recordBloom`` mints into the pool for that card. The contract
    computes ``happiness * rarityMultiplier(rarity)``, and both inputs come from the
    card the contract was handed, so recomputing it here cannot drift.

``pool_total(cards)`` / genesis burn
    The running totals: the Claim Pool fills by each card's yield while the Genesis
    Rain drains by a flat fee per bloom. They move in opposite directions on purpose —
    the payer and the earner are never the same purse, which is what makes the burn
    real rather than decorative (``docs/PLAN.md`` §8).

The multipliers are duplicated from Solidity rather than imported, because there is no
shared runtime between them. ``tests/api/test_economy.py`` asserts the table against
the values in ``chain/script/Deploy.s.sol``, so the copies cannot silently diverge.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.codec import Card

#: Mirrors `_multipliers()` in chain/script/Deploy.s.sol, indexed by rarity name.
RARITY_MULTIPLIERS: dict[str, int] = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 4,
    "EPIC": 8,
    "LEGENDARY": 20,
    "MYTHIC": 100,
}

#: Pre-minted, never refilled. 365_000 / 100 = 3_650 blooms = ten years to the day.
GENESIS_RAIN_TOTAL = 365_000
BLOOM_FEE = 100
MAX_BLOOMS = 3_650


def smile_yield(card: Card) -> int:
    """The whole $SMILE a bloom of ``card`` mints into the Claim Pool.

    Whole tokens, not wei: the contract multiplies by 1e18 on its side, and the site
    has no reason to carry eighteen zeros around.
    """
    return card.happiness * RARITY_MULTIPLIERS[card.rarity]


def pool_total(cards: Iterable[Card]) -> int:
    """Total $SMILE minted into the Claim Pool across every bloom so far."""
    return sum(smile_yield(card) for card in cards)


def genesis_burned(bloom_count: int) -> int:
    """$SMILE destroyed out of the Genesis Rain, one flat fee per bloom."""
    return min(GENESIS_RAIN_TOTAL, bloom_count * BLOOM_FEE)


def genesis_remaining(bloom_count: int) -> int:
    """What is left of the finite reserve. Only ever decreases."""
    return max(0, GENESIS_RAIN_TOTAL - genesis_burned(bloom_count))
