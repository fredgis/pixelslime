"""Recording the economic half of a bloom: ``ClaimPool.recordBloom``.

Anchoring and blooming are two different acts on two different tokens, which is why
they live in two different modules:

* :mod:`app.chain.anchor` mints the **SLIME** card — an ERC-721, one per slime, never
  repeatable, and the thing the site's provenance view points at.
* This module moves **SMILE** — the ERC-20 currency. One call burns the flat fee out
  of the finite Genesis Rain and mints the card's yield into the Claim Pool.

The yield is deliberately *not* supplied by this code. The backend passes only the
card's rarity and happiness, and the contract multiplies them itself. A backend key is
a far softer target than a contract, so letting it name the payout would make an
unlimited mint one leaked secret away (``docs/PLAN.md`` §8.10).
"""

from __future__ import annotations

from typing import Any

from app.codec import RARITIES
from app.core.logging import get_logger

from .errors import AnchorError
from .signer import Signer

_log = get_logger(__name__)

#: Minimal ABI: the one state-changing call plus the two counters worth reading back.
POOL_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "recordBloom",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "serial", "type": "uint256"},
            {"name": "rarity", "type": "uint8"},
            {"name": "happiness", "type": "uint256"},
        ],
        "outputs": [{"name": "yieldMinted", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "yieldByCard",
        "stateMutability": "view",
        "inputs": [{"name": "serial", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalYieldMinted",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def rarity_index(rarity: str) -> int:
    """Map a rarity name onto the Solidity ``enum Rarity`` ordinal.

    ``RARITIES`` and ``chain/src/Rarity.sol`` are declared in the same order, and
    ``tests/chain/test_claim_pool_writer.py`` pins that agreement — an off-by-one here
    would silently pay a card at the wrong multiplier.
    """
    try:
        return RARITIES.index(rarity)
    except ValueError as exc:
        raise AnchorError(f"unknown rarity {rarity!r}") from exc


class ClaimPoolWriter:
    """Calls ``recordBloom`` on the deployed Claim Pool."""

    def __init__(
        self,
        web3: Any,
        pool_address: str,
        signer: Signer,
        *,
        chain_id: int,
        gas_limit: int = 300_000,
        abi: list[dict[str, Any]] | None = None,
    ) -> None:
        self._web3 = web3
        self._signer = signer
        self._chain_id = chain_id
        self._gas_limit = gas_limit
        self._contract = web3.eth.contract(address=pool_address, abi=abi or POOL_ABI)

    def already_recorded(self, serial: int) -> bool:
        """True when this serial has already minted yield, so a re-run can skip it."""
        return int(self._contract.functions.yieldByCard(serial).call()) > 0

    def _fee_fields(self) -> dict[str, int]:
        try:
            priority = int(self._web3.eth.max_priority_fee)
        except Exception:  # a node may not implement eth_maxPriorityFeePerGas
            priority = 2_000_000_000
        base_fee = int(self._web3.eth.get_block("latest")["baseFeePerGas"])
        return {"maxPriorityFeePerGas": priority, "maxFeePerGas": base_fee * 2 + priority}

    def record_bloom(self, serial: int, rarity: str, happiness: int) -> bytes | None:
        """Burn the fee and mint the yield for ``serial``. Idempotent on the serial.

        Returns the transaction hash, or ``None`` when the bloom was already recorded.
        Raises :class:`AnchorError` if the transaction reverts — most likely because
        the Treasury has not approved the pool to burn, or because the Genesis Rain is
        exhausted, both of which need a human rather than a retry.
        """
        if self.already_recorded(serial):
            _log.info("bloom_skip_already_recorded", serial=serial)
            return None

        address = self._signer.address
        tx: dict[str, Any] = {
            "from": address,
            "nonce": int(self._web3.eth.get_transaction_count(address)),
            "chainId": self._chain_id,
            "type": 2,
            # An explicit limit rather than an estimate: estimation against a public
            # Amoy node intermittently fails on this call even though it executes fine.
            "gas": self._gas_limit,
            **self._fee_fields(),
        }
        call = self._contract.functions.recordBloom(serial, rarity_index(rarity), happiness)
        built: dict[str, Any] = dict(call.build_transaction(tx))
        signed = self._signer.sign_transaction(built)
        tx_hash = bytes(self._web3.eth.send_raw_transaction(signed.raw_transaction))

        receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash)
        status = int(receipt["status"])
        if status != 1:
            raise AnchorError(f"recordBloom for serial {serial} reverted (status {status})")
        _log.info(
            "bloom_confirmed",
            serial=serial,
            rarity=rarity,
            happiness=happiness,
            tx="0x" + tx_hash.hex(),
        )
        return tx_hash
