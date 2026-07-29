"""Shared fixtures and fakes for the chain tests — uniquely named to avoid clashes.

The module is deliberately called ``_chain_helpers`` (not ``_helpers``) so it can
never collide with another package's helper during collection. It carries:

* a **fixed known vector** — a private key, a digest, and the canonical low-``s``
  ``(v, r, s)`` it must produce — computed once with ``eth_keys`` and frozen here so
  the signer is pinned to an external reference, not to its own output;
* a tiny **fake web3** that records what the :class:`~app.chain.anchor.Anchorer`
  sends, so idempotency can be asserted without a live node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Known signer vector (see tests/chain/test_signer.py) ────────────────────
# Not a real key. Generated once with eth_keys.PrivateKey(...).sign_msg_hash(...).
KV_PRIVATE_KEY = "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"
KV_ADDRESS = "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23"
KV_DIGEST = bytes.fromhex("825da00c6e86d20dc590aa3e520365b3bae22508f61452259aa6df26f4591c57")
KV_R = 0x58A05BDBF59A4E7865E72902C27928B4551E711D6AC1F25221492A4EE882CC0C
KV_S_LOW = 0x413AE5B3CF5CDFF10D91A00DB65BD99C159E9117851AEF4D2FFFC9E5163E38C3
KV_V = 27  # recovery id 0 → 27
# The malleable upper-half counterpart of the same signature.
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
KV_S_HIGH = SECP256K1_N - KV_S_LOW

# A card-of-the-day-ish hash used across anchor tests (32 bytes).
SAMPLE_CARD_HASH = bytes.fromhex("c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")


class _FakeContractFunction:
    """A bound contract call that returns a canned value or a built tx dict."""

    def __init__(self, name: str, node: FakeNode, args: tuple[Any, ...]) -> None:
        self._name = name
        self._node = node
        self._args = args

    def call(self) -> Any:
        if self._name == "cardHash":
            serial = self._args[0]
            return self._node.minted.get(serial, b"\x00" * 32)
        raise AssertionError(f"unexpected .call() on {self._name}")  # pragma: no cover

    def build_transaction(self, tx: dict[str, Any]) -> dict[str, Any]:
        built = dict(tx)
        built["to"] = self._node.card_address
        built["value"] = 0
        # A recognisable data blob; the fake signer does not inspect it.
        built["data"] = b"\xab\xcd\xef\x01"
        return built


class _FakeFunctions:
    def __init__(self, node: FakeNode) -> None:
        self._node = node

    def cardHash(self, serial: int) -> _FakeContractFunction:
        return _FakeContractFunction("cardHash", self._node, (serial,))

    def mintCard(self, serial: int, card_hash: bytes, uri: str) -> _FakeContractFunction:
        return _FakeContractFunction("mintCard", self._node, (serial, card_hash, uri))


class _FakeContract:
    def __init__(self, node: FakeNode) -> None:
        self.functions = _FakeFunctions(node)


class _FakeEth:
    def __init__(self, node: FakeNode) -> None:
        self._node = node

    def contract(self, address: str, abi: list[dict[str, Any]]) -> _FakeContract:
        self._node.card_address = address
        return _FakeContract(self._node)

    @property
    def max_priority_fee(self) -> int:
        return 1_500_000_000

    def get_block(self, _which: str) -> dict[str, Any]:
        return {"baseFeePerGas": 10_000_000_000}

    def get_transaction_count(self, _address: str) -> int:
        return self._node.nonce

    def send_raw_transaction(self, raw: bytes) -> bytes:
        self._node.sent.append(raw)
        return self._node.tx_hash

    def wait_for_transaction_receipt(self, tx_hash: bytes) -> dict[str, Any]:
        return {"status": self._node.receipt_status, "blockNumber": self._node.block_number}


@dataclass
class FakeNode:
    """A minimal ``web3``-shaped fake that records sends for idempotency assertions."""

    minted: dict[int, bytes] = field(default_factory=dict)
    sent: list[bytes] = field(default_factory=list)
    nonce: int = 7
    tx_hash: bytes = b"\x11" * 32
    block_number: int = 4_321_000
    receipt_status: int = 1
    card_address: str = "0x000000000000000000000000000000000000dEaD"

    def __post_init__(self) -> None:
        self.eth = _FakeEth(self)

    def mark_minted(self, serial: int, card_hash: bytes) -> None:
        self.minted[serial] = card_hash


class FakeSigner:
    """A deterministic signer stand-in that records how often it signs a tx."""

    def __init__(self, address: str) -> None:
        self._address = address
        self.sign_count = 0

    @property
    def address(self) -> str:
        return self._address

    def sign_hash(self, message_hash: bytes) -> Any:  # pragma: no cover - unused here
        raise AssertionError("FakeSigner.sign_hash should not be called by anchor tests")

    def sign_transaction(self, transaction: dict[str, Any]) -> Any:
        self.sign_count += 1
        from app.chain.signer import Signature, SignedTransaction

        return SignedTransaction(
            raw_transaction=b"\x02\xf0raw",
            tx_hash=b"\x11" * 32,
            signature=Signature(v=27, r=KV_R, s=KV_S_LOW),
        )
