// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {W9EconomyFixture} from "./W9EconomyFixture.sol";
import {SmileToken} from "../src/SmileToken.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";

contract SmileTokenTest is W9EconomyFixture {
    function setUp() public {
        _deployEconomy();
    }

    function test_GenesisRainMintedOnceToTreasury() public view {
        assertEq(smile.GENESIS_RAIN(), 365_000 ether, "genesis rain constant");
        assertEq(smile.totalSupply(), 365_000 ether, "supply equals the one decree");
        assertEq(smile.balanceOf(treasury), 365_000 ether, "all of it sits in the Treasury");
        // 365,000 / 100 = 3,650 blooms = exactly ten years.
        assertEq(smile.GENESIS_RAIN() / 100 ether, 3_650, "runway is exactly 3,650 blooms");
    }

    function test_TreasuryHasNoMinterRoleAfterConstruction() public view {
        assertFalse(
            smile.hasRole(smile.MINTER_ROLE(), treasury),
            "the Treasury's minter role must be renounced in the constructor"
        );
    }

    /// The headline guarantee: the puddle provably cannot be refilled.
    function test_TreasuryCannotRefillTheGenesisRain() public {
        vm.prank(treasury);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, treasury, MINTER_ROLE
            )
        );
        smile.mint(treasury, 1 ether);
    }

    /// Not even the token admin can mint — the admin governs roles, it is not a minter.
    function test_AdminCannotMintDirectly() public {
        vm.prank(admin);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, admin, MINTER_ROLE
            )
        );
        smile.mint(admin, 1 ether);
    }

    /// Even if governance is fully renounced, the only minter left (the pool) can
    /// never mint to the Treasury, so the "finite puddle" holds for good.
    function test_AfterAdminRenouncedNoNewMinterCanBeGranted() public {
        vm.prank(admin);
        smile.renounceRole(DEFAULT_ADMIN_ROLE, admin);

        vm.prank(admin);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, admin, DEFAULT_ADMIN_ROLE
            )
        );
        smile.grantRole(MINTER_ROLE, treasury);
    }

    function test_OnlyPoolMayMint() public {
        // The pool holds MINTER_ROLE and mints into itself via recordBloom.
        assertTrue(smile.hasRole(smile.MINTER_ROLE(), address(pool)), "pool is the minter");
        vm.prank(address(pool));
        smile.mint(address(pool), 5 ether);
        assertEq(smile.balanceOf(address(pool)), 5 ether);
    }

    function test_BurnReducesSupplyAndBalance() public {
        vm.prank(treasury);
        smile.burn(100 ether);
        assertEq(smile.totalSupply(), 365_000 ether - 100 ether);
        assertEq(smile.balanceOf(treasury), 365_000 ether - 100 ether);
    }

    function test_ConstructorRejectsZeroAddresses() public {
        vm.expectRevert(SmileToken.ZeroAddress.selector);
        new SmileToken(address(0), admin);
        vm.expectRevert(SmileToken.ZeroAddress.selector);
        new SmileToken(treasury, address(0));
    }

    function test_CannotBurnMoreThanBalance() public {
        vm.prank(treasury);
        vm.expectRevert(
            abi.encodeWithSelector(
                IERC20Errors.ERC20InsufficientBalance.selector,
                treasury,
                365_000 ether,
                365_001 ether
            )
        );
        smile.burn(365_001 ether);
    }
}
