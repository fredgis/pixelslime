"""Anchor a card on-chain: build ``mintCard``, send it, wait, and report back.

This is the single write path from the backend to the ``PixelSlimeCard`` contract.
It is deliberately **idempotent**: a card is minted at most once, so before sending
anything it asks the contract whether the serial already carries a ``cardHash`` and,
if so, returns without broadcasting a second transaction. Re-running a failed batch
therefore never double-mints and never wastes gas.

The transaction is signed by an injected :class:`~app.chain.signer.Signer` — in
production the Key Vault HSM signer — so the raw key never touches this module.
Every log line is bound to the card serial via :func:`app.core.logging.card_context`,
per ``docs/AGENTS.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.logging import card_context, get_logger

from .anchor_row import AnchorResult
from .errors import AnchorError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .signer import Signer

_log = get_logger(__name__)

_ZERO_HASH = b"\x00" * 32

# The slice of the PixelSlimeCard ABI this module needs: the mint call and the
# cardHash getter used for the idempotency probe.
CARD_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "mintCard",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "serial", "type": "uint256"},
            {"name": "cardHash", "type": "bytes32"},
            {"name": "uri", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "cardHash",
        "stateMutability": "view",
        "inputs": [{"name": "serial", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    # Needed by find_mint: recovering a mint whose asmDB row was lost means reading
    # it back out of chain history, and web3 cannot filter logs for an event the ABI
    # does not describe.
    {
        "type": "event",
        "name": "Transfer",
        "anonymous": False,
        "inputs": [
            {"name": "from", "type": "address", "indexed": True},
            {"name": "to", "type": "address", "indexed": True},
            {"name": "tokenId", "type": "uint256", "indexed": True},
        ],
    },
]


@dataclass(frozen=True)
class AnchorReceipt:
    """The outcome of an anchor attempt.

    ``already_minted`` distinguishes a fresh mint (``tx_hash``/``block_number``
    populated) from an idempotent no-op (both ``None`` — the card was minted by an
    earlier run and no transaction was sent this time).
    """

    serial: int
    token_id: int
    card_hash: bytes
    already_minted: bool
    tx_hash: bytes | None = None
    block_number: int | None = None

    def to_anchor_result(self) -> AnchorResult:
        """Project onto the :class:`AnchorResult` an anchor row is built from.

        Raises :class:`AnchorError` for an idempotent no-op, which carries no fresh
        transaction to anchor — the row was written when the mint first landed.
        """
        if self.tx_hash is None or self.block_number is None:
            raise AnchorError("no transaction to anchor: the serial was already minted")
        return AnchorResult(
            serial=self.serial,
            tx_hash=self.tx_hash,
            block_number=self.block_number,
            token_id=self.token_id,
            card_hash=self.card_hash,
        )


class Anchorer:
    """Mints cards into the Vault via an injected signer, idempotently."""

    def __init__(
        self,
        web3: Any,
        card_address: str,
        signer: Signer,
        *,
        chain_id: int,
        gas_limit: int = 250_000,
        abi: list[dict[str, Any]] | None = None,
    ) -> None:
        self._web3 = web3
        self._signer = signer
        self._chain_id = chain_id
        self._gas_limit = gas_limit
        self._contract = web3.eth.contract(address=card_address, abi=abi or CARD_ABI)

    def is_minted(self, serial: int) -> bool:
        """True when the contract already stores a non-zero ``cardHash`` for ``serial``."""
        existing = self._contract.functions.cardHash(serial).call()
        return bytes(existing) != _ZERO_HASH

    def _fee_fields(self) -> dict[str, int]:
        """Derive EIP-1559 fee caps from the latest block, with a sane priority tip."""
        try:
            priority = int(self._web3.eth.max_priority_fee)
        except Exception:  # a node may not implement eth_maxPriorityFeePerGas
            priority = 2_000_000_000  # 2 gwei
        base_fee = int(self._web3.eth.get_block("latest")["baseFeePerGas"])
        return {
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base_fee * 2 + priority,
        }

    def _build_mint_tx(self, serial: int, card_hash: bytes, token_uri: str) -> dict[str, Any]:
        """Assemble the unsigned type-2 ``mintCard`` transaction dict."""
        address = self._signer.address
        tx: dict[str, Any] = {
            "from": address,
            "nonce": int(self._web3.eth.get_transaction_count(address)),
            "chainId": self._chain_id,
            "type": 2,
            "gas": self._gas_limit,
            **self._fee_fields(),
        }
        call = self._contract.functions.mintCard(serial, card_hash, token_uri)
        built: dict[str, Any] = dict(call.build_transaction(tx))
        # eth_account's encoder rejects the 'from' key; the signer supplies the sender.
        built.pop("from", None)
        return built

    def anchor(self, serial: int, card_hash: bytes, token_uri: str) -> AnchorReceipt:
        """Mint ``serial`` into the Vault, or no-op if it is already on-chain.

        Returns an :class:`AnchorReceipt`. Raises :class:`AnchorError` if the mint
        transaction reverts (receipt status 0).
        """
        if len(card_hash) != 32:
            raise AnchorError(f"card hash must be 32 bytes, got {len(card_hash)}")

        with card_context(serial):
            if self.is_minted(serial):
                _log.info("anchor_skip_already_minted", serial=serial)
                return AnchorReceipt(
                    serial=serial,
                    token_id=serial,
                    card_hash=card_hash,
                    already_minted=True,
                )

            tx = self._build_mint_tx(serial, card_hash, token_uri)
            signed = self._signer.sign_transaction(tx)
            tx_hash = bytes(self._web3.eth.send_raw_transaction(signed.raw_transaction))
            _log.info("anchor_sent", serial=serial, tx_hash="0x" + tx_hash.hex())

            receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash)
            status = int(receipt["status"])
            if status != 1:
                raise AnchorError(f"mint of serial {serial} reverted (status {status})")

            block_number = int(receipt["blockNumber"])
            _log.info("anchor_confirmed", serial=serial, block=block_number)
            return AnchorReceipt(
                serial=serial,
                token_id=serial,
                card_hash=card_hash,
                already_minted=False,
                tx_hash=tx_hash,
                block_number=block_number,
            )

    def find_mint(
        self,
        serial: int,
        *,
        lookback_blocks: int = 200_000,
        chunk_size: int = 900,
    ) -> AnchorResult | None:
        """Recover the transaction that first minted ``serial``, from chain history.

        A mint cannot be repeated, so when a card is on-chain but its anchor row is
        missing — the process died between the two writes — the only way to complete
        the record is to go and read back what already happened. Returns ``None`` when
        no mint is found within ``lookback_blocks``, which the caller treats as "leave
        it pending" rather than inventing a commitment.

        The search walks backwards in ``chunk_size`` windows because public RPC
        providers reject wide ``eth_getLogs`` ranges outright (Amoy's public node
        answers a 200k-block span with a bare 403). Walking backwards also finds the
        most recent mints — the ones a retry is most likely to be chasing — first.
        """
        if not self.is_minted(serial):
            return None

        latest = int(self._web3.eth.block_number)
        floor = max(0, latest - lookback_blocks)
        high = latest
        while high >= floor:
            low = max(floor, high - chunk_size + 1)
            found = self._find_mint_in_range(serial, low, high)
            if found is not None:
                return found
            if low == floor:
                break
            high = low - 1

        _log.warning("anchor_mint_log_not_found", serial=serial, from_block=floor)
        return None

    def _find_mint_in_range(self, serial: int, low: int, high: int) -> AnchorResult | None:
        """Scan one block window for the Transfer that created ``serial``."""
        try:
            logs = self._contract.events.Transfer().get_logs(
                from_block=low,
                to_block=high,
                argument_filters={"tokenId": serial},
            )
        except Exception as exc:  # an RPC may cap the range or reject the filter
            _log.warning("anchor_find_mint_failed", serial=serial, error=str(exc))
            return None

        # The mint is the Transfer out of the zero address; later trades share the id.
        for entry in logs:
            if int(str(entry["args"]["from"]), 16) != 0:
                continue
            return AnchorResult(
                serial=serial,
                tx_hash=bytes(entry["transactionHash"]),
                block_number=int(entry["blockNumber"]),
                token_id=int(entry["args"]["tokenId"]),
                card_hash=bytes(self._contract.functions.cardHash(serial).call()),
            )
        return None
