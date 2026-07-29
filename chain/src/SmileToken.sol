// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title SmileToken — the $SMILE ERC-20 (the "Genesis Rain").
/// @notice The economic heart of PIXELSLIME (`docs/PLAN.md` §8.3). Exactly
///         `GENESIS_RAIN` tokens are minted **once** to the Treasury at
///         construction; the Treasury's ability to mint is then removed, so the
///         puddle is finite and provably cannot be refilled.
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
    ///         after the constructor returns.
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
    ///        "cannot be refilled" guarantee would be a fiction rather than a fact.
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
    /// @dev This is the only inflation path. The Treasury is not a minter, so it
    ///      cannot use this to refill the puddle — see the constructor.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }
}
