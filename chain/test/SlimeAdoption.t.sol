// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {W9EconomyFixture} from "./W9EconomyFixture.sol";
import {SlimeAdoption} from "../src/SlimeAdoption.sol";
import {Rarity} from "../src/Rarity.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {IERC20Errors} from "@openzeppelin/contracts/interfaces/draft-IERC6093.sol";

contract SlimeAdoptionTest is W9EconomyFixture {
    bytes32 internal constant HASH = keccak256("adopt-stream");

    function setUp() public {
        _deployEconomy();
        _mint(1, HASH); // one card sitting in the Vault
        // Give Alice some spending money out of the Treasury's Genesis Rain.
        vm.prank(treasury);
        assertTrue(smile.transfer(alice, 10_000 ether));
    }

    function _list(uint256 serial, Rarity rarity) internal {
        adoption.list(serial, rarity); // test holds LISTER_ROLE
    }

    function test_TierPricesMatchPlan() public view {
        assertEq(adoption.tierPrice(Rarity.COMMON), 200 ether);
        assertEq(adoption.tierPrice(Rarity.UNCOMMON), 400 ether);
        assertEq(adoption.tierPrice(Rarity.RARE), 900 ether);
        assertEq(adoption.tierPrice(Rarity.EPIC), 2_000 ether);
        assertEq(adoption.tierPrice(Rarity.LEGENDARY), 6_000 ether);
        assertEq(adoption.tierPrice(Rarity.MYTHIC), 25_000 ether);
    }

    function test_AdoptBurnsSmileAndTransfersCardOutOfVault() public {
        _list(1, Rarity.COMMON); // 200 $SMILE
        uint256 supplyBefore = smile.totalSupply();

        vm.startPrank(alice);
        smile.approve(address(adoption), 200 ether);
        adoption.adopt(1);
        vm.stopPrank();

        assertEq(card.ownerOf(1), alice, "card leaves the Vault");
        assertEq(smile.balanceOf(alice), 10_000 ether - 200 ether, "buyer paid the tier price");
        assertEq(smile.totalSupply(), supplyBefore - 200 ether, "the price was burned, not banked");
        assertEq(adoption.priceOf(1), 0, "delisted after adoption");
    }

    function test_AdoptUnlistedReverts() public {
        vm.startPrank(alice);
        smile.approve(address(adoption), 200 ether);
        vm.expectRevert(abi.encodeWithSelector(SlimeAdoption.NotListed.selector, 1));
        adoption.adopt(1);
        vm.stopPrank();
    }

    function test_CannotAdoptTwice() public {
        _list(1, Rarity.COMMON);
        vm.startPrank(alice);
        smile.approve(address(adoption), 1_000 ether);
        adoption.adopt(1);
        vm.expectRevert(abi.encodeWithSelector(SlimeAdoption.NotListed.selector, 1));
        adoption.adopt(1);
        vm.stopPrank();
    }

    function test_AdoptWithoutAllowanceReverts() public {
        _list(1, Rarity.COMMON);
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(
                IERC20Errors.ERC20InsufficientAllowance.selector, address(adoption), 0, 200 ether
            )
        );
        adoption.adopt(1);
    }

    function test_ListingACardNotInVaultReverts() public {
        // Adopt it away first, so the Vault no longer owns it.
        _list(1, Rarity.COMMON);
        vm.startPrank(alice);
        smile.approve(address(adoption), 200 ether);
        adoption.adopt(1);
        vm.stopPrank();

        vm.expectRevert(abi.encodeWithSelector(SlimeAdoption.NotInVault.selector, 1));
        _list(1, Rarity.COMMON);
    }

    function test_UnlistPreventsAdoption() public {
        _list(1, Rarity.RARE);
        adoption.unlist(1);
        vm.startPrank(alice);
        smile.approve(address(adoption), 1_000 ether);
        vm.expectRevert(abi.encodeWithSelector(SlimeAdoption.NotListed.selector, 1));
        adoption.adopt(1);
        vm.stopPrank();
    }

    function test_OnlyListerCanList() public {
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, alice, LISTER_ROLE
            )
        );
        adoption.list(1, Rarity.COMMON);
    }

    function test_ParamsCanRetuneTierPrice() public {
        vm.prank(admin);
        adoption.setTierPrice(Rarity.COMMON, 123 ether);
        _list(1, Rarity.COMMON);
        assertEq(adoption.priceOf(1), 123 ether);
    }
}
