// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {W9EconomyFixture} from "./W9EconomyFixture.sol";
import {ClaimPool} from "../src/ClaimPool.sol";
import {Rarity} from "../src/Rarity.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";

contract ClaimPoolTest is W9EconomyFixture {
    function setUp() public {
        _deployEconomy();
    }

    // ── recordBloom: the two halves of the economy, on two different purses ──────

    /// The headline economic test: one bloom burns exactly the Bloom Fee from the
    /// Treasury and mints the yield into the pool — never the reverse.
    function test_BloomBurnsExactly100AndMintsYieldToPoolNotTreasury() public {
        uint256 treasuryBefore = smile.balanceOf(treasury);
        uint256 poolBefore = smile.balanceOf(address(pool));
        uint256 supplyBefore = smile.totalSupply();

        // RARE (×4) at 75 happiness → 300 $SMILE of yield.
        vm.prank(bloomer);
        uint256 minted = pool.recordBloom(1, Rarity.RARE, 75);

        assertEq(minted, 300 ether, "yield = happiness x rarityMultiplier");
        assertEq(
            smile.balanceOf(treasury), treasuryBefore - 100 ether, "Treasury shrinks by exactly 100"
        );
        assertGt(treasuryBefore, smile.balanceOf(treasury), "Treasury only ever goes down");
        assertEq(smile.balanceOf(address(pool)), poolBefore + 300 ether, "yield lands in the pool");
        assertEq(pool.yieldByCard(1), 300 ether);
        assertEq(pool.totalYieldMinted(), 300 ether);
        // Net supply moves by (yield - fee): +300 minted, -100 burned.
        assertEq(smile.totalSupply(), supplyBefore + 300 ether - 100 ether);
    }

    function test_YieldFollowsRarityMultipliers() public {
        uint256[6] memory expected = [uint256(75), 150, 300, 600, 1500, 7500];
        for (uint256 i = 0; i < 6; ++i) {
            vm.prank(bloomer);
            uint256 minted = pool.recordBloom(100 + i, Rarity(i), 75);
            assertEq(minted, expected[i] * 1 ether, "multiplier per tier");
        }
    }

    function test_OnlyBloomRoleCanRecordBloom() public {
        vm.prank(treasury);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, treasury, BLOOM_ROLE
            )
        );
        pool.recordBloom(1, Rarity.COMMON, 50);
    }

    function test_HappinessOutOfRangeReverts() public {
        vm.prank(bloomer);
        vm.expectRevert(abi.encodeWithSelector(ClaimPool.HappinessOutOfRange.selector, 101));
        pool.recordBloom(1, Rarity.COMMON, 101);
    }

    // ── claim: the voucher path ─────────────────────────────────────────────────

    function _fundPool() internal {
        // MYTHIC (×100) at 100 happiness → 10,000 $SMILE minted into the pool.
        vm.prank(bloomer);
        pool.recordBloom(1, Rarity.MYTHIC, 100);
    }

    function _voucher(address wallet, uint256 serial, uint256 amount, uint256 nonce)
        internal
        view
        returns (ClaimPool.ClaimVoucher memory)
    {
        return ClaimPool.ClaimVoucher({
            wallet: wallet,
            serial: serial,
            amount: amount,
            nonce: nonce,
            deadline: block.timestamp + 1 hours
        });
    }

    function test_ClaimPaysWalletFromPool() public {
        _fundPool();
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        bytes memory sig = _sign(v, signerPk);

        uint256 poolBefore = smile.balanceOf(address(pool));
        pool.claim(v, sig); // anyone may relay a valid voucher
        assertEq(smile.balanceOf(alice), 1_000 ether, "wallet is paid");
        assertEq(smile.balanceOf(address(pool)), poolBefore - 1_000 ether, "pool debited");
        assertEq(pool.claimedByWallet(alice), 1_000 ether);
        assertEq(pool.claimedByCard(1), 1_000 ether);
        assertTrue(pool.nonceUsed(1));
    }

    /// A voucher cannot be replayed: the nonce is single-use.
    function test_ReplayedNonceReverts() public {
        _fundPool();
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        bytes memory sig = _sign(v, signerPk);

        pool.claim(v, sig);
        vm.expectRevert(abi.encodeWithSelector(ClaimPool.NonceAlreadyUsed.selector, 1));
        pool.claim(v, sig);
    }

    /// A voucher signed by the wrong key is rejected.
    function test_WrongKeySignatureReverts() public {
        _fundPool();
        uint256 wrongPk = uint256(keccak256("not.the.signer"));
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        bytes memory sig = _sign(v, wrongPk);

        vm.expectRevert(ClaimPool.BadVoucherSignature.selector);
        pool.claim(v, sig);
    }

    /// Tampering with any field after signing invalidates the signature.
    function test_TamperedVoucherReverts() public {
        _fundPool();
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        bytes memory sig = _sign(v, signerPk);
        v.amount = 9_000 ether; // attacker inflates the payout
        vm.expectRevert(ClaimPool.BadVoucherSignature.selector);
        pool.claim(v, sig);
    }

    function test_ExpiredVoucherReverts() public {
        _fundPool();
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        v.deadline = block.timestamp - 1;
        bytes memory sig = _sign(v, signerPk);
        vm.expectRevert(abi.encodeWithSelector(ClaimPool.VoucherExpired.selector, v.deadline));
        pool.claim(v, sig);
    }

    function test_ZeroAmountReverts() public {
        _fundPool();
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 0, 1);
        bytes memory sig = _sign(v, signerPk);
        vm.expectRevert(ClaimPool.ZeroAmount.selector);
        pool.claim(v, sig);
    }

    function test_PerWalletCapEnforced() public {
        _fundPool();
        vm.prank(admin);
        pool.setCaps(500 ether, 50_000 ether); // tighten wallet cap only

        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 600 ether, 1);
        bytes memory sig = _sign(v, signerPk);
        vm.expectRevert(
            abi.encodeWithSelector(ClaimPool.WalletCapExceeded.selector, alice, 600 ether, 500 ether)
        );
        pool.claim(v, sig);
    }

    function test_PerCardCapEnforced() public {
        _fundPool();
        vm.prank(admin);
        pool.setCaps(100_000 ether, 400 ether); // tighten card cap only

        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 600 ether, 1);
        bytes memory sig = _sign(v, signerPk);
        vm.expectRevert(
            abi.encodeWithSelector(ClaimPool.CardCapExceeded.selector, 1, 600 ether, 400 ether)
        );
        pool.claim(v, sig);
    }

    function test_CapAccumulatesAcrossVouchers() public {
        _fundPool();
        vm.prank(admin);
        pool.setCaps(1_000 ether, 50_000 ether);

        ClaimPool.ClaimVoucher memory v1 = _voucher(alice, 1, 700 ether, 1);
        pool.claim(v1, _sign(v1, signerPk));

        // 700 already claimed; a further 400 would breach the 1,000 wallet cap.
        ClaimPool.ClaimVoucher memory v2 = _voucher(alice, 2, 400 ether, 2);
        bytes memory sig2 = _sign(v2, signerPk);
        vm.expectRevert(
            abi.encodeWithSelector(
                ClaimPool.WalletCapExceeded.selector, alice, 1_100 ether, 1_000 ether
            )
        );
        pool.claim(v2, sig2);
    }

    function test_ClaimBeyondPoolBalanceReverts() public {
        _fundPool(); // 10,000 in the pool
        vm.prank(admin);
        pool.setCaps(1_000_000 ether, 1_000_000 ether);
        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 20_000 ether, 1);
        bytes memory sig = _sign(v, signerPk);
        vm.expectRevert(
            abi.encodeWithSelector(ClaimPool.PoolExhausted.selector, 20_000 ether, 10_000 ether)
        );
        pool.claim(v, sig);
    }

    function test_SignerRotationInvalidatesOldKey() public {
        _fundPool();
        uint256 newPk = uint256(keccak256("rotated.signer"));
        address newSigner = vm.addr(newPk);
        vm.prank(admin);
        pool.setSigner(newSigner);

        ClaimPool.ClaimVoucher memory v = _voucher(alice, 1, 1_000 ether, 1);
        bytes memory oldSig = _sign(v, signerPk);
        bytes memory newSig = _sign(v, newPk);

        // Old key now rejected.
        vm.expectRevert(ClaimPool.BadVoucherSignature.selector);
        pool.claim(v, oldSig);
        // New key accepted.
        pool.claim(v, newSig);
        assertEq(smile.balanceOf(alice), 1_000 ether);
    }

    // ── the Treasury cannot drain the pool ──────────────────────────────────────

    /// The pool has no owner/admin withdrawal path, the Treasury holds none of its
    /// roles, and it is not the voucher signer — so it cannot extract a single wei.
    function test_TreasuryCannotDrainThePool() public {
        _fundPool();
        uint256 poolBalance = smile.balanceOf(address(pool));
        assertGt(poolBalance, 0);

        // It holds none of the pool's roles.
        assertFalse(pool.hasRole(DEFAULT_ADMIN_ROLE, treasury));
        assertFalse(pool.hasRole(PARAMS_ROLE, treasury));
        assertFalse(pool.hasRole(BLOOM_ROLE, treasury));

        // It cannot tune caps or point the signer at itself.
        vm.prank(treasury);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, treasury, PARAMS_ROLE
            )
        );
        pool.setSigner(treasury);

        // A voucher the Treasury signs itself is not signed by {signer}.
        ClaimPool.ClaimVoucher memory v = _voucher(treasury, 1, poolBalance, 99);
        uint256 treasuryPk = uint256(keccak256("treasury.tries.to.self.sign"));
        bytes memory selfSig = _sign(v, treasuryPk);
        vm.prank(treasury);
        vm.expectRevert(ClaimPool.BadVoucherSignature.selector);
        pool.claim(v, selfSig);

        // It has no ERC-20 allowance to pull the pool's balance either.
        vm.prank(treasury);
        vm.expectRevert(
            abi.encodeWithSelector(
                IERC20Errors.ERC20InsufficientAllowance.selector, treasury, 0, poolBalance
            )
        );
        // forge-lint: disable-next-line(erc20-unchecked-transfer)
        smile.transferFrom(address(pool), treasury, poolBalance);

        assertEq(smile.balanceOf(address(pool)), poolBalance, "pool balance is untouched");
    }
}
