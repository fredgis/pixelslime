// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {W9EconomyFixture} from "./W9EconomyFixture.sol";
import {ClaimPool} from "../src/ClaimPool.sol";
import {Rarity} from "../src/Rarity.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";
import {console2} from "forge-std/console2.sol";

/// @notice End-to-end economic properties: the ten-year runway closes to exactly
///         zero, the Treasury only ever shrinks, and the full loop (bloom → claim →
///         adopt) settles the way `docs/PLAN.md` §8 says it should.
contract EconomyIntegrationTest is W9EconomyFixture {
    function setUp() public {
        _deployEconomy();
    }

    /// The whole point of 365,000 ÷ 100: after 3,650 blooms the Genesis Rain is
    /// exactly zero, and the 3,651st bloom cannot happen. This walks the plan's own
    /// rarity census (trimmed by one COMMON to land on 3,650) at 75 happiness, so
    /// it also checks the "≈905,000 $SMILE at the end" figure from §8.6.
    function test_3650BloomsDrainGenesisRainToExactlyZero() public {
        uint256[6] memory census = [uint256(1642), 986, 621, 292, 91, 18];
        uint256[6] memory mult = [uint256(1), 2, 4, 8, 20, 100];
        uint256 happiness = 75;

        uint256 totalBlooms;
        uint256 expectedYield;
        uint256 serial = 1;

        vm.startPrank(bloomer);
        for (uint256 tier = 0; tier < 6; ++tier) {
            for (uint256 k = 0; k < census[tier]; ++k) {
                pool.recordBloom(serial, Rarity(tier), happiness);
                expectedYield += happiness * mult[tier] * 1 ether;
                ++serial;
                ++totalBlooms;
            }
        }
        vm.stopPrank();

        assertEq(totalBlooms, 3_650, "exactly ten years of daily slimes");
        assertEq(smile.balanceOf(treasury), 0, "the Genesis Rain is completely gone");
        assertEq(smile.GENESIS_RAIN(), 3_650 * 100 ether, "365,000 = 3,650 x 100, arithmetic closes");

        // Everything still in existence was minted from slime happiness, and all of
        // it lives in the pool (nothing has been claimed yet).
        assertEq(pool.totalYieldMinted(), expectedYield, "on-chain yield matches the formula");
        assertEq(smile.totalSupply(), expectedYield, "the only supply left is earned yield");
        assertEq(smile.balanceOf(address(pool)), expectedYield, "all yield sits in the pool");
        assertEq(expectedYield, 904_050 ether, "the census yields ~905k $SMILE (plan figure)");

        console2.log("Genesis Rain remaining (wei):", smile.balanceOf(treasury));
        console2.log("Total $SMILE in existence at year 10 (whole):", expectedYield / 1 ether);

        // The 3,651st bloom cannot burn a fee that no longer exists.
        vm.prank(bloomer);
        vm.expectRevert(
            abi.encodeWithSelector(
                IERC20Errors.ERC20InsufficientBalance.selector, treasury, 0, 100 ether
            )
        );
        pool.recordBloom(3_651, Rarity.COMMON, happiness);
    }

    /// The Treasury balance is monotonically non-increasing across a run of blooms —
    /// the yield never flows back into the purse that pays the fee.
    function test_TreasuryBalanceIsMonotonicallyNonIncreasing() public {
        uint256 previous = smile.balanceOf(treasury);
        vm.startPrank(bloomer);
        for (uint256 i = 1; i <= 50; ++i) {
            pool.recordBloom(i, Rarity(i % 6), 80);
            uint256 current = smile.balanceOf(treasury);
            assertLe(current, previous, "Treasury never grows");
            assertEq(previous - current, 100 ether, "each bloom costs exactly the fee");
            previous = current;
        }
        vm.stopPrank();
    }

    /// The loop closes: a bloom mints yield, a voucher pays a Keeper, and the Keeper
    /// spends that $SMILE to adopt a slime out of the Vault — burning it for good.
    function test_FullLoop_BloomThenClaimThenAdopt() public {
        // Two cards bloom; card 2 is the one Alice will end up adopting (COMMON, 200).
        _mint(1, keccak256("stream-1"));
        _mint(2, keccak256("stream-2"));

        vm.startPrank(bloomer);
        pool.recordBloom(1, Rarity.MYTHIC, 100); // 10,000 into the pool
        pool.recordBloom(2, Rarity.COMMON, 60); // 60 into the pool
        vm.stopPrank();

        // Alice claims 500 $SMILE via a signed voucher.
        ClaimPool.ClaimVoucher memory v = ClaimPool.ClaimVoucher({
            wallet: alice,
            serial: 1,
            amount: 500 ether,
            nonce: 1,
            deadline: block.timestamp + 1 hours
        });
        pool.claim(v, _sign(v, signerPk));
        assertEq(smile.balanceOf(alice), 500 ether);

        // Alice adopts card 2 for 200 $SMILE, which is burned.
        adoption.list(2, Rarity.COMMON);
        uint256 supplyBefore = smile.totalSupply();
        vm.startPrank(alice);
        smile.approve(address(adoption), 200 ether);
        adoption.adopt(2);
        vm.stopPrank();

        assertEq(card.ownerOf(2), alice, "the slime is adopted out of the Vault");
        assertEq(smile.balanceOf(alice), 300 ether, "200 spent of the 500 claimed");
        assertEq(smile.totalSupply(), supplyBefore - 200 ether, "the adoption price is burned");
    }
}
