// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title Rarity — the six PixelSlime tiers, as an on-chain enum.
/// @notice The ordinals are frozen and match `RARITIES` in the PSC-1 codec
///         (`backend/app/codec/card.py`) and `docs/PLAN.md` §2.4 exactly. They are
///         the index into every rarity-keyed array in this project (yield
///         multipliers, adoption tier prices), so they must never be reordered.
enum Rarity {
    COMMON, // 0
    UNCOMMON, // 1
    RARE, // 2
    EPIC, // 3
    LEGENDARY, // 4
    MYTHIC // 5
}

uint256 constant RARITY_COUNT = 6;
