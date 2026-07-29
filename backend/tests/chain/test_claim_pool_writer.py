"""The rarity ordinal must agree with Solidity, or cards are paid the wrong yield.

``ClaimPool.recordBloom`` takes a ``uint8`` enum. Python sends an index. If the two
orderings ever drift, nothing errors — an EPIC card would simply be paid at RARE's
multiplier, quietly and forever. That makes this agreement worth a test of its own.
"""

from __future__ import annotations

import pytest

from app.chain.bloom import rarity_index
from app.chain.errors import AnchorError

# Lifted from chain/src/Rarity.sol, which numbers its enum in declaration order.
SOLIDITY_ORDINALS = {
    "COMMON": 0,
    "UNCOMMON": 1,
    "RARE": 2,
    "EPIC": 3,
    "LEGENDARY": 4,
    "MYTHIC": 5,
}


@pytest.mark.parametrize(("rarity", "ordinal"), sorted(SOLIDITY_ORDINALS.items()))
def test_rarity_ordinals_match_solidity(rarity: str, ordinal: int) -> None:
    assert rarity_index(rarity) == ordinal


def test_mochibo_is_epic_which_is_three() -> None:
    # The value actually sent on Amoy in tx 0xa29bcec7…f6276ac7, which minted 760
    # SMILE = happiness 95 x 8. A different ordinal would have paid a different sum.
    assert rarity_index("EPIC") == 3


def test_an_unknown_rarity_is_refused_rather_than_guessed() -> None:
    with pytest.raises(AnchorError, match="unknown rarity"):
        rarity_index("ULTRA")
