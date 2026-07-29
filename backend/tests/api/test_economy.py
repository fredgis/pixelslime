"""The $SMILE a card generates, mirrored from ClaimPool.recordBloom.

The contract computes ``happiness * rarityMultiplier(rarity)``. Because both inputs
live on the card itself, the site can show the same number without asking the chain —
and the two can never disagree, since the contract is fed from this very card.

These tests pin the mirror to the *contract's* table rather than to whatever the
Python happens to do, so a change on one side without the other fails here.
"""

from __future__ import annotations

import pytest

from _api_helpers import build_card
from app.core.economy import RARITY_MULTIPLIERS, smile_yield

# Lifted from chain/script/Deploy.s.sol `_multipliers()` — the deployed values.
CONTRACT_MULTIPLIERS = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 4,
    "EPIC": 8,
    "LEGENDARY": 20,
    "MYTHIC": 100,
}


def test_multipliers_match_the_deployed_contract() -> None:
    assert RARITY_MULTIPLIERS == CONTRACT_MULTIPLIERS


def test_mochibo_yields_what_the_chain_actually_minted() -> None:
    # Verified on Polygon Amoy: recordBloom(1, EPIC, 95) minted 760 $SMILE
    # (tx 0xa29bcec720a3d34c5973c07fb3b186345c4343ca25cbe5ce9e202676f6276ac7).
    card = build_card(1, rarity="EPIC", happiness=95)
    assert smile_yield(card) == 760


@pytest.mark.parametrize(
    ("rarity", "happiness", "expected"),
    [
        ("COMMON", 50, 50),
        ("MYTHIC", 100, 10_000),
        ("LEGENDARY", 0, 0),
    ],
)
def test_yield_is_happiness_times_the_multiplier(
    rarity: str, happiness: int, expected: int
) -> None:
    assert smile_yield(build_card(1, rarity=rarity, happiness=happiness)) == expected
