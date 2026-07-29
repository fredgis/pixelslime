// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SmileToken} from "./SmileToken.sol";
import {PixelSlimeCard} from "./PixelSlimeCard.sol";
import {Rarity, RARITY_COUNT} from "./Rarity.sol";

/// @title SlimeAdoption — the $SMILE sink that finally lets a slime leave the Vault.
/// @notice CHAIN 3 · ADOPT (`docs/PLAN.md` §8.5, §8.7). A visitor spends $SMILE to
///         adopt a listed slime: the tier price is **burned** from the buyer and the
///         card is transferred out of the Vault into their wallet. Adoption is the
///         real demand-side sink — it is what finally gives $SMILE something to be
///         *for* — and, like the Bloom Fee, it only ever destroys tokens.
/// @dev The Vault must `setApprovalForAll(thisContract, true)` on the card
///      collection, and the buyer must `approve` this contract for the tier price
///      of $SMILE, before {adopt} can succeed.
contract SlimeAdoption is AccessControl, ReentrancyGuard {
    /// @notice May list Vault-held cards for adoption (the pipeline / an operator).
    bytes32 public constant LISTER_ROLE = keccak256("LISTER_ROLE");
    /// @notice May tune the six tier prices after deployment (the §8.5 PARAMS holder).
    bytes32 public constant PARAMS_ROLE = keccak256("PARAMS_ROLE");

    /// @notice The $SMILE token burned on adoption.
    SmileToken public immutable smile;
    /// @notice The card collection whose tokens are adopted out of the Vault.
    PixelSlimeCard public immutable card;
    /// @notice The Vault that owns not-yet-adopted cards.
    address public immutable vault;

    uint256[RARITY_COUNT] private _tierPrice;

    /// @notice The $SMILE price to adopt a given serial, or 0 if it is not listed.
    mapping(uint256 serial => uint256) public priceOf;

    event TierPricesUpdated(uint256[RARITY_COUNT] tierPrices);
    event Listed(uint256 indexed serial, Rarity rarity, uint256 price);
    event Unlisted(uint256 indexed serial);
    event Adopted(uint256 indexed serial, address indexed adopter, uint256 price);

    error ZeroAddress();
    error BadTierPriceCount();
    error NotInVault(uint256 serial);
    error NotListed(uint256 serial);

    /// @param smile_ The $SMILE token.
    /// @param card_ The PixelSlime card collection.
    /// @param admin Governance / role administrator.
    /// @param tierPrices_ The six adoption prices, in `Rarity` order.
    constructor(
        SmileToken smile_,
        PixelSlimeCard card_,
        address admin,
        uint256[] memory tierPrices_
    ) {
        if (address(smile_) == address(0) || address(card_) == address(0) || admin == address(0)) {
            revert ZeroAddress();
        }
        if (tierPrices_.length != RARITY_COUNT) {
            revert BadTierPriceCount();
        }
        smile = smile_;
        card = card_;
        vault = card_.vault();
        for (uint256 i = 0; i < RARITY_COUNT; ++i) {
            _tierPrice[i] = tierPrices_[i];
        }
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(PARAMS_ROLE, admin);
    }

    /// @notice The adoption price for a rarity tier (COMMON 200 … MYTHIC 25,000).
    function tierPrice(Rarity rarity) public view returns (uint256) {
        return _tierPrice[uint256(rarity)];
    }

    /// @notice List a Vault-held card for adoption at its rarity's tier price.
    /// @dev `LISTER_ROLE`-gated. Reverts if the card is not currently in the Vault,
    ///      so a card cannot be listed twice or listed after it has been adopted.
    function list(uint256 serial, Rarity rarity) external onlyRole(LISTER_ROLE) {
        if (card.ownerOf(serial) != vault) {
            revert NotInVault(serial);
        }
        uint256 price = tierPrice(rarity);
        priceOf[serial] = price;
        emit Listed(serial, rarity, price);
    }

    /// @notice Remove a card from adoption. `LISTER_ROLE`-gated.
    function unlist(uint256 serial) external onlyRole(LISTER_ROLE) {
        if (priceOf[serial] == 0) {
            revert NotListed(serial);
        }
        delete priceOf[serial];
        emit Unlisted(serial);
    }

    /// @notice Adopt a listed slime: burn the tier price, receive the card.
    /// @dev Checks-effects-interactions and `nonReentrant`. The listing is cleared
    ///      *before* the external token calls so a re-entrant callback (via
    ///      `onERC721Received`) cannot adopt the same card twice.
    function adopt(uint256 serial) external nonReentrant {
        uint256 price = priceOf[serial];
        if (price == 0) {
            revert NotListed(serial);
        }
        delete priceOf[serial];

        smile.burnFrom(msg.sender, price);
        card.safeTransferFrom(vault, msg.sender, serial);
        emit Adopted(serial, msg.sender, price);
    }

    /// @notice Tune a single tier's adoption price. `PARAMS_ROLE`-gated.
    function setTierPrice(Rarity rarity, uint256 price) external onlyRole(PARAMS_ROLE) {
        _tierPrice[uint256(rarity)] = price;
        emit TierPricesUpdated(_tierPrice);
    }
}
