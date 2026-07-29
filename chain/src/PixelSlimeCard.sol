// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721URIStorage} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import {ERC2981} from "@openzeppelin/contracts/token/common/ERC2981.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title PixelSlimeCard — the daily card as an ERC-721 (CHAIN 1 · ANCHOR).
/// @notice One token per daily slime, minted into the Vault (`docs/PLAN.md` §8.5,
///         §8.7, §8.11). `tokenId == serial`, and each token permanently records
///         `cardHash`, the keccak256 of the card's canonical PSC-1 byte stream
///         (`docs/CODEC.md` §6). That hash is the whole point of the anchor: it
///         proves a given slime existed exactly as it is, on that date, without
///         duplicating a single byte of the 175-byte payload on-chain.
contract PixelSlimeCard is ERC721URIStorage, ERC2981, AccessControl {
    /// @notice Holders of this role may mint cards (the daily pipeline job).
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    /// @notice Holders of this role may tune royalty settings after deployment.
    bytes32 public constant PARAMS_ROLE = keccak256("PARAMS_ROLE");

    /// @notice The Vault every card is minted into. There is nobody to airdrop to,
    ///         so all cards begin their life here and only leave via {SlimeAdoption}.
    address public immutable vault;

    /// @notice keccak256 of the card's PSC-1 stream, by serial. The on-chain anchor.
    mapping(uint256 serial => bytes32) public cardHash;

    /// @notice Emitted once per successful mint, carrying the anchor hash so an
    ///         indexer can reconstruct provenance without reading storage.
    event CardMinted(uint256 indexed serial, bytes32 cardHash, string tokenURI);

    /// @dev A serial may be minted at most once; the anchor is immutable.
    error SerialAlreadyMinted(uint256 serial);
    /// @dev The card hash must be the real keccak256 of a stream, never zero.
    error EmptyCardHash(uint256 serial);
    /// @dev Raised if a constructor address is the zero address.
    error ZeroAddress();

    /// @param vault_ The Treasury / Vault that owns every freshly minted card.
    /// @param admin The governance address that administers roles.
    /// @param royaltyReceiver Where EIP-2981 royalties are paid (typically the Vault).
    /// @param royaltyFeeNumerator Royalty in basis points of 10_000 (e.g. 500 = 5%).
    constructor(
        address vault_,
        address admin,
        address royaltyReceiver,
        uint96 royaltyFeeNumerator
    ) ERC721("PixelSlime Card", "SLIME") {
        if (vault_ == address(0) || admin == address(0) || royaltyReceiver == address(0)) {
            revert ZeroAddress();
        }
        vault = vault_;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(PARAMS_ROLE, admin);
        _setDefaultRoyalty(royaltyReceiver, royaltyFeeNumerator);
    }

    /// @notice Mint the card of the day into the Vault and anchor its hash.
    /// @dev `MINTER_ROLE`-gated and idempotent by design: a duplicate `serial`
    ///      reverts with {SerialAlreadyMinted} rather than silently re-minting, so
    ///      the pipeline's catch-up job can safely retry without double-anchoring.
    /// @param serial The card serial; becomes the `tokenId` verbatim.
    /// @param cardHash_ keccak256 of the full PSC-1 stream for this card.
    /// @param uri The metadata URI, pointing at `/api/nft/{serial}`.
    function mintCard(uint256 serial, bytes32 cardHash_, string calldata uri)
        external
        onlyRole(MINTER_ROLE)
    {
        if (cardHash_ == bytes32(0)) {
            revert EmptyCardHash(serial);
        }
        if (_ownerOf(serial) != address(0) || cardHash[serial] != bytes32(0)) {
            revert SerialAlreadyMinted(serial);
        }
        cardHash[serial] = cardHash_;
        _safeMint(vault, serial);
        _setTokenURI(serial, uri);
        emit CardMinted(serial, cardHash_, uri);
    }

    /// @notice Update the collection-wide royalty. `PARAMS_ROLE`-gated (§8.5).
    function setDefaultRoyalty(address receiver, uint96 feeNumerator)
        external
        onlyRole(PARAMS_ROLE)
    {
        _setDefaultRoyalty(receiver, feeNumerator);
    }

    /// @dev Combine the ERC-165 tables of every parent that declares one.
    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721URIStorage, ERC2981, AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
