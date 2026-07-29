// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {SmileToken} from "../src/SmileToken.sol";
import {PixelSlimeCard} from "../src/PixelSlimeCard.sol";
import {ClaimPool} from "../src/ClaimPool.sol";
import {SlimeAdoption} from "../src/SlimeAdoption.sol";

/// @title Deploy — the PIXELSLIME economy, to Polygon Amoy (or a local Anvil).
/// @notice Broadcasts as the *governance* deployer, which becomes the `admin`
///         (DEFAULT_ADMIN_ROLE) of every contract. The Treasury/Vault is a
///         **separate** address on purpose: if `admin == treasury` the Treasury
///         could re-grant itself SmileToken.MINTER_ROLE and refill the Genesis
///         Rain, so the script refuses to run in that configuration.
///
///         Role grants that governance owns are wired here. The two *Treasury*
///         approvals (letting the pool burn Bloom Fees, letting adoption move the
///         Vault's cards) are deliberately **not** performed here — they belong to
///         the Treasury key and gate steps 2 and 3 of the rollout. The exact
///         commands are printed at the end and documented in the W9 report.
///
///         Required env:
///           DEPLOYER_PRIVATE_KEY   governance key, funded from the Amoy faucet
///           TREASURY_ADDRESS       the Vault: holds the Genesis Rain + all cards
///           VOUCHER_SIGNER_ADDRESS ClaimPool EIP-712 signer (Key Vault key addr)
///           MINTER_ADDRESS         backend anchor account (gets card MINTER_ROLE)
///           BLOOM_RECORDER_ADDRESS backend account (gets pool BLOOM_ROLE)
///         Optional env (sensible defaults):
///           LISTER_ADDRESS (=MINTER_ADDRESS), ROYALTY_RECEIVER (=TREASURY_ADDRESS),
///           ROYALTY_BPS (=500), MAX_CLAIM_PER_WALLET, MAX_CLAIM_PER_CARD
contract Deploy is Script {
    uint256 internal constant DEFAULT_MAX_PER_WALLET = 100_000 ether;
    uint256 internal constant DEFAULT_MAX_PER_CARD = 50_000 ether;
    uint256 internal constant DEFAULT_ROYALTY_BPS = 500; // 5%

    struct Addresses {
        address treasury;
        address admin;
        address signer;
        address minter;
        address bloomer;
        address lister;
        address royaltyReceiver;
    }

    function run() external {
        uint256 deployerPk = vm.envUint("DEPLOYER_PRIVATE_KEY");

        Addresses memory a;
        a.admin = vm.addr(deployerPk);
        a.treasury = vm.envAddress("TREASURY_ADDRESS");
        a.signer = vm.envAddress("VOUCHER_SIGNER_ADDRESS");
        a.minter = vm.envAddress("MINTER_ADDRESS");
        a.bloomer = vm.envAddress("BLOOM_RECORDER_ADDRESS");
        a.lister = vm.envOr("LISTER_ADDRESS", a.minter);
        a.royaltyReceiver = vm.envOr("ROYALTY_RECEIVER", a.treasury);
        uint96 royaltyBps = uint96(vm.envOr("ROYALTY_BPS", DEFAULT_ROYALTY_BPS));
        uint256 maxPerWallet = vm.envOr("MAX_CLAIM_PER_WALLET", DEFAULT_MAX_PER_WALLET);
        uint256 maxPerCard = vm.envOr("MAX_CLAIM_PER_CARD", DEFAULT_MAX_PER_CARD);

        require(a.admin != a.treasury, "admin must differ from treasury (refill guarantee)");
        require(a.treasury != address(0), "treasury is zero");
        require(a.signer != address(0), "voucher signer is zero");
        require(a.minter != address(0), "minter is zero");

        vm.startBroadcast(deployerPk);

        SmileToken smile = new SmileToken(a.treasury, a.admin);
        PixelSlimeCard card = new PixelSlimeCard(a.treasury, a.admin, a.royaltyReceiver, royaltyBps);
        ClaimPool pool = new ClaimPool(
            smile, a.treasury, a.admin, a.signer, _multipliers(), maxPerWallet, maxPerCard
        );
        SlimeAdoption adoption = new SlimeAdoption(smile, card, a.admin, _tierPrices());

        // Only the pool may mint $SMILE — and only into itself (the ClaimPool).
        smile.grantRole(smile.MINTER_ROLE(), address(pool));
        // The backend anchor account may mint cards into the Vault.
        card.grantRole(card.MINTER_ROLE(), a.minter);
        // The backend may record blooms (burn 100 + mint yield) once step 2 is live.
        pool.grantRole(pool.BLOOM_ROLE(), a.bloomer);
        // The backend may list cards for adoption once step 3 is live.
        adoption.grantRole(adoption.LISTER_ROLE(), a.lister);

        vm.stopBroadcast();

        _record(smile, card, pool, adoption, a);
    }

    function _multipliers() internal pure returns (uint256[] memory m) {
        m = new uint256[](6);
        m[0] = 1;
        m[1] = 2;
        m[2] = 4;
        m[3] = 8;
        m[4] = 20;
        m[5] = 100;
    }

    function _tierPrices() internal pure returns (uint256[] memory p) {
        p = new uint256[](6);
        p[0] = 200 ether;
        p[1] = 400 ether;
        p[2] = 900 ether;
        p[3] = 2_000 ether;
        p[4] = 6_000 ether;
        p[5] = 25_000 ether;
    }

    function _record(
        SmileToken smile,
        PixelSlimeCard card,
        ClaimPool pool,
        SlimeAdoption adoption,
        Addresses memory a
    ) internal {
        string memory obj = "pixelslime";
        vm.serializeUint(obj, "chainId", block.chainid);
        vm.serializeAddress(obj, "SmileToken", address(smile));
        vm.serializeAddress(obj, "PixelSlimeCard", address(card));
        vm.serializeAddress(obj, "ClaimPool", address(pool));
        vm.serializeAddress(obj, "SlimeAdoption", address(adoption));
        vm.serializeAddress(obj, "treasury", a.treasury);
        vm.serializeAddress(obj, "admin", a.admin);
        vm.serializeAddress(obj, "voucherSigner", a.signer);
        vm.serializeAddress(obj, "minter", a.minter);
        string memory json = vm.serializeAddress(obj, "bloomRecorder", a.bloomer);
        vm.writeJson(json, "./deployments/amoy.json");

        console2.log("== PIXELSLIME deployed ==");
        console2.log("chainId       ", block.chainid);
        console2.log("SmileToken    ", address(smile));
        console2.log("PixelSlimeCard", address(card));
        console2.log("ClaimPool     ", address(pool));
        console2.log("SlimeAdoption ", address(adoption));
        console2.log("-- Treasury must run these to enable steps 2 and 3 --");
        console2.log("  step 2 (blooms):   smile.approve(ClaimPool, type(uint256).max)");
        console2.log("  step 3 (adoption): card.setApprovalForAll(SlimeAdoption, true)");
    }
}
