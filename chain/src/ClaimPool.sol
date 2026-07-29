// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {SmileToken} from "./SmileToken.sol";
import {Rarity, RARITY_COUNT} from "./Rarity.sol";

/// @title ClaimPool — where slime happiness accrues, and only leaves by voucher.
/// @notice The right-hand branch of `docs/PLAN.md` §8.3. Every bloom does two
///         things here, atomically, and they touch two different purses:
///
///         1. it burns the **Bloom Fee** (100 $SMILE) out of the Treasury's finite
///            Genesis Rain — `burnFrom(treasury)` destroys tokens, it does not move
///            them here, so the Treasury genuinely shrinks; and
///         2. it mints **new** $SMILE — `happiness × rarityMultiplier` — into *this*
///            pool, which the Treasury has no authority to spend.
///
///         That is the whole trick: the payer (Treasury) and the earner (this pool)
///         are never the same purse, so the fee is a real cost and not theatre.
///         Payouts leave only against an EIP-712 voucher signed by the backend's
///         Key Vault key, with per-wallet and per-card caps and single-use nonces
///         enforced here on-chain. There is deliberately **no** owner/admin path
///         that can withdraw the pool — see the contract's absence of any sweep.
contract ClaimPool is AccessControl, EIP712, ReentrancyGuard {
    /// @notice Records blooms (mints yield / burns the fee): the pipeline job.
    bytes32 public constant BLOOM_ROLE = keccak256("BLOOM_ROLE");
    /// @notice Tunes caps and rotates the voucher signer (the §8.5 PARAMS holder).
    bytes32 public constant PARAMS_ROLE = keccak256("PARAMS_ROLE");

    /// @notice The Bloom Fee burned from the Treasury on every single bloom.
    ///         `GENESIS_RAIN / BLOOM_FEE = 3,650` — exactly ten years of daily slimes.
    uint256 public constant BLOOM_FEE = 100 ether;
    /// @notice One whole $SMILE, the yield unit (`happiness × multiplier` whole tokens).
    uint256 public constant ONE_SMILE = 1 ether;
    /// @notice Happiness is a 0..100 stat in the codec; reject anything larger loudly.
    uint256 public constant MAX_HAPPINESS = 100;

    /// @notice EIP-712 type of a payout voucher. `deadline` is included (the plan's
    ///         §8.4 tuple omits it) so a leaked voucher cannot be redeemed forever.
    bytes32 public constant CLAIM_TYPEHASH =
        keccak256("Claim(address wallet,uint256 serial,uint256 amount,uint256 nonce,uint256 deadline)");

    /// @notice The $SMILE token this pool mints and pays out.
    SmileToken public immutable smile;
    /// @notice The Treasury whose Genesis Rain funds each Bloom Fee burn.
    address public immutable treasury;

    /// @notice The address whose signature authorises a payout (the Key Vault key).
    address public signer;
    /// @notice Cumulative payout ceiling per receiving wallet.
    uint256 public maxClaimPerWallet;
    /// @notice Cumulative payout ceiling per card serial.
    uint256 public maxClaimPerCard;

    uint256[RARITY_COUNT] private _rarityMultiplier;

    /// @notice Total yield ever minted into the pool (analytics + supply proofs).
    uint256 public totalYieldMinted;
    /// @notice Total $SMILE ever paid out of the pool.
    uint256 public totalClaimed;

    mapping(address wallet => uint256) public claimedByWallet;
    mapping(uint256 serial => uint256) public claimedByCard;
    mapping(uint256 serial => uint256) public yieldByCard;
    mapping(uint256 nonce => bool) public nonceUsed;

    /// @notice Whether a serial's bloom has been recorded, independently of its yield.
    /// @dev Kept separate from `yieldByCard` on purpose. A card with zero happiness
    ///      mints nothing, so `yieldByCard` would stay at zero and any "already done?"
    ///      test built on it would wave the same serial through again and again,
    ///      burning the Bloom Fee each time. The flag records the *event*, not its size.
    mapping(uint256 serial => bool) public bloomRecorded;

    /// @notice A signed authorisation to withdraw `amount` from the pool.
    struct ClaimVoucher {
        address wallet;
        uint256 serial;
        uint256 amount;
        uint256 nonce;
        uint256 deadline;
    }

    event BloomRecorded(uint256 indexed serial, Rarity rarity, uint256 happiness, uint256 yieldMinted);
    event Claimed(address indexed wallet, uint256 indexed serial, uint256 amount, uint256 nonce);
    event SignerUpdated(address indexed previousSigner, address indexed newSigner);
    event CapsUpdated(uint256 maxClaimPerWallet, uint256 maxClaimPerCard);

    error ZeroAddress();
    error BadMultiplierCount();
    error HappinessOutOfRange(uint256 happiness);
    /// @dev Raised when a serial's bloom has already been recorded. Idempotency is
    ///      enforced here rather than by the caller, because the caller's only usable
    ///      signal was `yieldByCard > 0`, which a zero-happiness card never trips.
    error BloomAlreadyRecorded(uint256 serial);
    error VoucherExpired(uint256 deadline);
    error ZeroAmount();
    error BadVoucherSignature();
    error NonceAlreadyUsed(uint256 nonce);
    error WalletCapExceeded(address wallet, uint256 requested, uint256 cap);
    error CardCapExceeded(uint256 serial, uint256 requested, uint256 cap);
    error PoolExhausted(uint256 requested, uint256 available);

    /// @param smile_ The $SMILE token. This pool must hold its `MINTER_ROLE`.
    /// @param treasury_ The Treasury; must `approve` this pool to burn its fees.
    /// @param admin Governance / role administrator.
    /// @param signer_ The initial voucher-signing address (the Key Vault key).
    /// @param multipliers_ The six rarity yield multipliers, in `Rarity` order.
    /// @param maxClaimPerWallet_ Initial per-wallet payout cap.
    /// @param maxClaimPerCard_ Initial per-card payout cap.
    constructor(
        SmileToken smile_,
        address treasury_,
        address admin,
        address signer_,
        uint256[] memory multipliers_,
        uint256 maxClaimPerWallet_,
        uint256 maxClaimPerCard_
    ) EIP712("PixelSlimeClaimPool", "1") {
        if (
            address(smile_) == address(0) || treasury_ == address(0) || admin == address(0)
                || signer_ == address(0)
        ) {
            revert ZeroAddress();
        }
        if (multipliers_.length != RARITY_COUNT) {
            revert BadMultiplierCount();
        }
        smile = smile_;
        treasury = treasury_;
        signer = signer_;
        maxClaimPerWallet = maxClaimPerWallet_;
        maxClaimPerCard = maxClaimPerCard_;
        for (uint256 i = 0; i < RARITY_COUNT; ++i) {
            _rarityMultiplier[i] = multipliers_[i];
        }
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(PARAMS_ROLE, admin);
    }

    /// @notice The yield multiplier for a rarity tier (COMMON 1 … MYTHIC 100).
    function rarityMultiplier(Rarity rarity) public view returns (uint256) {
        return _rarityMultiplier[uint256(rarity)];
    }

    /// @notice The pool's current spendable balance of $SMILE.
    function poolBalance() external view returns (uint256) {
        return smile.balanceOf(address(this));
    }

    /// @notice Record one bloom: burn the fee from the Treasury and mint the yield.
    /// @dev `BLOOM_ROLE`-gated. The two halves are deliberately in one transaction
    ///      so the invariant "the Treasury shrinks, the pool grows, and never the
    ///      reverse" is enforced atomically and is trivially auditable.
    /// @param serial The blooming card's serial.
    /// @param rarity The card's rarity tier (selects the multiplier).
    /// @param happiness The card's happiness stat (0..100).
    /// @return yieldMinted The $SMILE minted into the pool for this bloom.
    function recordBloom(uint256 serial, Rarity rarity, uint256 happiness)
        external
        onlyRole(BLOOM_ROLE)
        returns (uint256 yieldMinted)
    {
        if (happiness > MAX_HAPPINESS) {
            revert HappinessOutOfRange(happiness);
        }
        // The ten-year calendar is exactly 365,000 / 100, so a serial that burns the
        // fee twice does not merely double-count -- it removes a day from the end of
        // the schedule. A retry after an RPC timeout that actually succeeded is the
        // ordinary way this happens, so it is refused here rather than left to the
        // caller to remember.
        if (bloomRecorded[serial]) {
            revert BloomAlreadyRecorded(serial);
        }
        bloomRecorded[serial] = true;

        // Left branch: the Treasury's finite puddle shrinks by exactly the fee.
        smile.burnFrom(treasury, BLOOM_FEE);

        // Right branch: brand-new happiness, minted to THIS pool — never the Treasury.
        yieldMinted = happiness * rarityMultiplier(rarity) * ONE_SMILE;
        if (yieldMinted > 0) {
            smile.mint(address(this), yieldMinted);
            yieldByCard[serial] += yieldMinted;
            totalYieldMinted += yieldMinted;
        }
        emit BloomRecorded(serial, rarity, happiness, yieldMinted);
    }

    /// @notice Redeem a signed voucher, paying `amount` from the pool to `wallet`.
    /// @dev Checks-effects-interactions and `nonReentrant`. Enforces: unexpired,
    ///      non-zero, signed by {signer}, unused nonce, within the per-wallet and
    ///      per-card caps. Anyone may relay a valid voucher; the signature — not the
    ///      caller — is the authority, which is what lets claiming stay login-free.
    function claim(ClaimVoucher calldata voucher, bytes calldata signature) external nonReentrant {
        if (block.timestamp > voucher.deadline) {
            revert VoucherExpired(voucher.deadline);
        }
        if (voucher.amount == 0) {
            revert ZeroAmount();
        }

        bytes32 digest = _hashTypedDataV4(
            keccak256(
                abi.encode(
                    CLAIM_TYPEHASH,
                    voucher.wallet,
                    voucher.serial,
                    voucher.amount,
                    voucher.nonce,
                    voucher.deadline
                )
            )
        );
        if (ECDSA.recover(digest, signature) != signer) {
            revert BadVoucherSignature();
        }
        if (nonceUsed[voucher.nonce]) {
            revert NonceAlreadyUsed(voucher.nonce);
        }

        uint256 walletTotal = claimedByWallet[voucher.wallet] + voucher.amount;
        if (walletTotal > maxClaimPerWallet) {
            revert WalletCapExceeded(voucher.wallet, walletTotal, maxClaimPerWallet);
        }
        uint256 cardTotal = claimedByCard[voucher.serial] + voucher.amount;
        if (cardTotal > maxClaimPerCard) {
            revert CardCapExceeded(voucher.serial, cardTotal, maxClaimPerCard);
        }

        uint256 available = smile.balanceOf(address(this));
        if (voucher.amount > available) {
            revert PoolExhausted(voucher.amount, available);
        }

        // Effects before the external token call.
        nonceUsed[voucher.nonce] = true;
        claimedByWallet[voucher.wallet] = walletTotal;
        claimedByCard[voucher.serial] = cardTotal;
        totalClaimed += voucher.amount;

        emit Claimed(voucher.wallet, voucher.serial, voucher.amount, voucher.nonce);
        SafeERC20.safeTransfer(smile, voucher.wallet, voucher.amount);
    }

    /// @notice Rotate the voucher-signing key. `PARAMS_ROLE`-gated.
    function setSigner(address newSigner) external onlyRole(PARAMS_ROLE) {
        if (newSigner == address(0)) {
            revert ZeroAddress();
        }
        emit SignerUpdated(signer, newSigner);
        signer = newSigner;
    }

    /// @notice Tune the payout caps. `PARAMS_ROLE`-gated (§8.5).
    function setCaps(uint256 maxClaimPerWallet_, uint256 maxClaimPerCard_)
        external
        onlyRole(PARAMS_ROLE)
    {
        maxClaimPerWallet = maxClaimPerWallet_;
        maxClaimPerCard = maxClaimPerCard_;
        emit CapsUpdated(maxClaimPerWallet_, maxClaimPerCard_);
    }
}
