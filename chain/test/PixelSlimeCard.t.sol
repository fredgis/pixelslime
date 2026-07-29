// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {W9EconomyFixture} from "./W9EconomyFixture.sol";
import {PixelSlimeCard} from "../src/PixelSlimeCard.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {IERC2981} from "@openzeppelin/contracts/interfaces/IERC2981.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";

contract PixelSlimeCardTest is W9EconomyFixture {
    bytes32 internal constant HASH_1 = keccak256("card-1-stream");
    bytes32 internal constant HASH_2 = keccak256("card-2-stream");

    function setUp() public {
        _deployEconomy();
    }

    function test_MintCardIntoVaultAndAnchorHash() public {
        _mint(1, HASH_1);
        assertEq(card.ownerOf(1), treasury, "minted into the Vault");
        assertEq(card.cardHash(1), HASH_1, "PSC-1 hash anchored");
        assertEq(card.tokenURI(1), "/api/nft/1", "tokenURI points at the API");
        assertEq(card.balanceOf(treasury), 1);
    }

    function test_TokenIdEqualsSerial() public {
        _mint(4242, HASH_1);
        // ownerOf(serial) resolving proves tokenId == serial.
        assertEq(card.ownerOf(4242), treasury);
    }

    /// A duplicate serial must revert — anchors are immutable, retries are safe.
    function test_DuplicateSerialReverts() public {
        _mint(1, HASH_1);
        vm.expectRevert(abi.encodeWithSelector(PixelSlimeCard.SerialAlreadyMinted.selector, 1));
        _mint(1, HASH_2);
        // The first anchor is untouched.
        assertEq(card.cardHash(1), HASH_1);
    }

    function test_EmptyHashReverts() public {
        vm.expectRevert(abi.encodeWithSelector(PixelSlimeCard.EmptyCardHash.selector, 7));
        _mint(7, bytes32(0));
    }

    function test_OnlyMinterMayMint() public {
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, alice, MINTER_ROLE
            )
        );
        card.mintCard(1, HASH_1, "/api/nft/1");
    }

    function test_Eip2981RoyaltyIsFivePercentToTreasury() public {
        _mint(1, HASH_1);
        (address receiver, uint256 amount) = card.royaltyInfo(1, 10_000 ether);
        assertEq(receiver, treasury, "royalty to the Vault");
        assertEq(amount, 500 ether, "5% of the sale price");
    }

    function test_SupportsExpectedInterfaces() public view {
        assertTrue(card.supportsInterface(type(IERC721).interfaceId), "ERC721");
        assertTrue(card.supportsInterface(type(IERC2981).interfaceId), "ERC2981");
        assertTrue(card.supportsInterface(type(IAccessControl).interfaceId), "AccessControl");
    }

    function test_ParamsRoleCanRetuneRoyalty() public {
        vm.prank(admin);
        card.setDefaultRoyalty(bob, 250); // 2.5%
        _mint(1, HASH_1);
        (address receiver, uint256 amount) = card.royaltyInfo(1, 10_000 ether);
        assertEq(receiver, bob);
        assertEq(amount, 250 ether);
    }

    function test_NonParamsCannotRetuneRoyalty() public {
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(
                IAccessControl.AccessControlUnauthorizedAccount.selector, alice, PARAMS_ROLE
            )
        );
        card.setDefaultRoyalty(alice, 10_000);
    }
}
