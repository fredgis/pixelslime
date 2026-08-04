// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title SmileToken — the $SMILE ERC-20 (the "Genesis Rain").
/// @notice The economic heart of PIXELSLIME (`docs/PLAN.md` §8.3). Exactly
///         `GENESIS_RAIN` tokens are minted **once** to the Treasury at
///         construction, and the Treasury's ability to mint is then removed for
///         good: `admin != treasury_` is enforced below, so no governance path
///         reachable by the Treasury can give it back. That much is a property of
///         this code.
///
///         What is **not** guaranteed by this code is the total supply. `MINTER_ROLE`
///         is administered by `DEFAULT_ADMIN_ROLE`, so the admin may grant minting
///         rights to any address — including itself — at any time. The 365,000 cap
///         is therefore a governance commitment, not a mathematical one, and any
///         claim that the puddle "provably cannot be refilled" would be false while
///         a live `DEFAULT_ADMIN_ROLE` holder exists. Making the cap real requires
///         renouncing that role, which is irreversible and hence a deliberate
///         decision rather than a deployment step; until then, treat the supply as
///         capped by policy and verify it on-chain rather than trusting this comment.
///
///         The two halves of the economy are kept on different purses on purpose:
///         the Treasury only ever *burns* (its balance is monotonically
///         non-increasing after deployment), while brand-new $SMILE is minted by a
///         separate `MINTER_ROLE` holder — the {ClaimPool} — into a pool the
///         Treasury has no authority over. That separation is what makes the Bloom
///         Fee a real cost rather than money moving inside one pocket.
contract SmileToken is ERC20, ERC20Burnable, AccessControl {
    /// @notice Holders of this role may mint new $SMILE. Granted post-deployment
    ///         to the {ClaimPool} only; the Treasury is deliberately never a member
    ///         after the constructor returns. Note this is not a closed set: the
    ///         `DEFAULT_ADMIN_ROLE` holder can add members, so "the ClaimPool is the
    ///         only minter" is a statement about the current on-chain state, to be
    ///         checked with `getRoleMemberCount`, not an invariant of this contract.
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    /// @notice The one and only decreed supply: 365,000 $SMILE (18 decimals).
    ///         `365,000 / 100 (Bloom Fee) = 3,650 blooms = exactly ten years`.
    uint256 public constant GENESIS_RAIN = 365_000 ether;

    /// @notice The Treasury (Vault) that received the Genesis Rain. Kept for
    ///         transparency and for off-chain "rain remaining" displays; it confers
    ///         no minting power.
    address public immutable treasury;

    /// @dev Raised if a constructor address is the zero address.
    error ZeroAddress();

    /// @dev Raised if `admin == treasury_`. Enforced here rather than left to the
    ///      deploy script, because an invariant that only holds when the caller
    ///      happens to use one particular script is not an invariant.
    error AdminMustDifferFromTreasury();

    /// @param treasury_ The Vault that holds the Genesis Rain.
    /// @param admin The governance address that administers roles (the PARAMS
    ///        holder of §8.5). It MUST differ from `treasury_`: were the Treasury
    ///        its own admin it could re-grant itself `MINTER_ROLE`, and the
    ///        separation between the burning purse and the minting purse would be
    ///        a fiction rather than a fact. Note this check constrains the
    ///        *Treasury* only — `admin` itself retains the power to grant
    ///        `MINTER_ROLE` to anyone, so choose it accordingly.
    constructor(address treasury_, address admin) ERC20("PixelSlime Smile", "SMILE") {
        if (treasury_ == address(0) || admin == address(0)) {
            revert ZeroAddress();
        }
        if (admin == treasury_) {
            revert AdminMustDifferFromTreasury();
        }
        treasury = treasury_;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);

        // Grant, use, and immediately renounce the Treasury's minting power. After
        // this constructor there is no code path — and, because `admin != treasury`
        // is now checked above rather than assumed, no governance path reachable by
        // the Treasury — that lets the Treasury mint again. The Genesis Rain is a
        // one-shot event.
        _grantRole(MINTER_ROLE, treasury_);
        _mint(treasury_, GENESIS_RAIN);
        _revokeRole(MINTER_ROLE, treasury_);
    }

    /// @notice Mint new $SMILE. Restricted to `MINTER_ROLE` (the {ClaimPool}).
    /// @dev This is the only inflation path, and the Treasury cannot reach it —
    ///      see the constructor. It is not, however, a supply cap: whoever holds
    ///      `DEFAULT_ADMIN_ROLE` can grant `MINTER_ROLE` and mint without limit.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }
}
