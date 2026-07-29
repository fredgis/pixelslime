// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {SmileToken} from "../src/SmileToken.sol";
import {PixelSlimeCard} from "../src/PixelSlimeCard.sol";
import {ClaimPool} from "../src/ClaimPool.sol";
import {SlimeAdoption} from "../src/SlimeAdoption.sol";

/// @title W9EconomyFixture — the shared PIXELSLIME economy, wired the way deploy will.
/// @notice Every test contract inherits this so the deployment sequence and role
///         grants live in exactly one place, mirroring `script/Deploy.s.sol`. The
///         name is prefixed `W9` to keep it unambiguous across the wider repo test
///         tree. It is `abstract`, so Foundry never treats it as a test itself.
abstract contract W9EconomyFixture is Test {
    SmileToken internal smile;
    PixelSlimeCard internal card;
    ClaimPool internal pool;
    SlimeAdoption internal adoption;

    address internal treasury = makeAddr("treasury");
    address internal admin = makeAddr("admin");
    address internal bloomer = makeAddr("bloomer");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    // The voucher-signing key stands in for the Key Vault secp256k1 key.
    uint256 internal signerPk = uint256(keccak256("pixelslime.voucher.signer"));
    address internal signerAddr;

    uint96 internal constant ROYALTY_BPS = 500; // 5%
    uint256 internal constant MAX_PER_WALLET = 100_000 ether;
    uint256 internal constant MAX_PER_CARD = 50_000 ether;

    // Role ids as compile-time constants. Tests use these rather than the on-chain
    // getters (`smile.MINTER_ROLE()`) inside a `vm.prank`/`vm.expectRevert` region:
    // Solidity evaluates such a getter as an *external call* which would consume the
    // prank / be caught by expectRevert before the call under test ever runs.
    bytes32 internal constant DEFAULT_ADMIN_ROLE = bytes32(0);
    bytes32 internal constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 internal constant PARAMS_ROLE = keccak256("PARAMS_ROLE");
    bytes32 internal constant BLOOM_ROLE = keccak256("BLOOM_ROLE");
    bytes32 internal constant LISTER_ROLE = keccak256("LISTER_ROLE");

    /// @dev The six rarity yield multipliers, COMMON→MYTHIC (`docs/PLAN.md` §8.5).
    function _multipliers() internal pure returns (uint256[] memory m) {
        m = new uint256[](6);
        m[0] = 1;
        m[1] = 2;
        m[2] = 4;
        m[3] = 8;
        m[4] = 20;
        m[5] = 100;
    }

    /// @dev The six adoption tier prices, COMMON→MYTHIC (`docs/PLAN.md` §8.5).
    function _tierPrices() internal pure returns (uint256[] memory p) {
        p = new uint256[](6);
        p[0] = 200 ether;
        p[1] = 400 ether;
        p[2] = 900 ether;
        p[3] = 2_000 ether;
        p[4] = 6_000 ether;
        p[5] = 25_000 ether;
    }

    function _deployEconomy() internal {
        signerAddr = vm.addr(signerPk);

        smile = new SmileToken(treasury, admin);
        card = new PixelSlimeCard(treasury, admin, treasury, ROYALTY_BPS);
        pool = new ClaimPool(
            smile, treasury, admin, signerAddr, _multipliers(), MAX_PER_WALLET, MAX_PER_CARD
        );
        adoption = new SlimeAdoption(smile, card, admin, _tierPrices());

        // Governance wires the roles. The Treasury is deliberately given no minting
        // authority anywhere — only the pool may mint (into itself).
        vm.startPrank(admin);
        smile.grantRole(smile.MINTER_ROLE(), address(pool));
        card.grantRole(card.MINTER_ROLE(), address(this));
        pool.grantRole(pool.BLOOM_ROLE(), bloomer);
        adoption.grantRole(adoption.LISTER_ROLE(), address(this));
        vm.stopPrank();

        // The Treasury allows the pool to burn its Bloom Fees, and the Vault lets
        // the adoption contract move its cards out on a successful adoption.
        vm.startPrank(treasury);
        smile.approve(address(pool), type(uint256).max);
        card.setApprovalForAll(address(adoption), true);
        vm.stopPrank();
    }

    /// @dev Mint a card into the Vault (the test contract holds `MINTER_ROLE`).
    function _mint(uint256 serial, bytes32 hash_) internal {
        card.mintCard(serial, hash_, string.concat("/api/nft/", vm.toString(serial)));
    }

    /// @dev EIP-712 digest for a voucher, computed independently of the contract so
    ///      the tests cross-check rather than restate its `_hashTypedDataV4`.
    function _voucherDigest(ClaimPool.ClaimVoucher memory v) internal view returns (bytes32) {
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("PixelSlimeClaimPool")),
                keccak256(bytes("1")),
                block.chainid,
                address(pool)
            )
        );
        bytes32 structHash = keccak256(
            abi.encode(pool.CLAIM_TYPEHASH(), v.wallet, v.serial, v.amount, v.nonce, v.deadline)
        );
        return keccak256(abi.encodePacked(hex"1901", domainSeparator, structHash));
    }

    /// @dev Sign a voucher with an arbitrary key (used for the wrong-key test too).
    function _sign(ClaimPool.ClaimVoucher memory v, uint256 pk)
        internal
        view
        returns (bytes memory)
    {
        (uint8 sv, bytes32 r, bytes32 s) = vm.sign(pk, _voucherDigest(v));
        return abi.encodePacked(r, s, sv);
    }
}
