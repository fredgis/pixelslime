"""The rarity ordinal must agree with Solidity, or cards are paid the wrong yield.

``ClaimPool.recordBloom`` takes a ``uint8`` enum. Python sends an index. If the two
orderings ever drift, nothing errors — an EPIC card would simply be paid at RARE's
multiplier, quietly and forever. That makes this agreement worth a test of its own.
"""

from __future__ import annotations

import pytest

from app.chain.bloom import rarity_index
from app.chain.errors import AnchorError

# Lifted from chain/src/Rarity.sol, which numbers its enum in declaration order.
SOLIDITY_ORDINALS = {
    "COMMON": 0,
    "UNCOMMON": 1,
    "RARE": 2,
    "EPIC": 3,
    "LEGENDARY": 4,
    "MYTHIC": 5,
}


@pytest.mark.parametrize(("rarity", "ordinal"), sorted(SOLIDITY_ORDINALS.items()))
def test_rarity_ordinals_match_solidity(rarity: str, ordinal: int) -> None:
    assert rarity_index(rarity) == ordinal


def test_mochibo_is_epic_which_is_three() -> None:
    # The value actually sent on Amoy in tx 0xa29bcec7…f6276ac7, which minted 760
    # SMILE = happiness 95 x 8. A different ordinal would have paid a different sum.
    assert rarity_index("EPIC") == 3


def test_an_unknown_rarity_is_refused_rather_than_guessed() -> None:
    with pytest.raises(AnchorError, match="unknown rarity"):
        rarity_index("ULTRA")


class _RecordingSigner:
    """Captures the transaction it is asked to sign."""

    address = "0x25A99633839fD88457Ce9AF690c19dAb7172B729"

    def __init__(self) -> None:
        self.seen: dict[str, object] = {}

    def sign_hash(self, message_hash: bytes) -> object:  # pragma: no cover - unused
        raise NotImplementedError

    def sign_transaction(self, transaction: dict[str, object]) -> object:
        self.seen = dict(transaction)
        raise _StopHere


class _StopHere(Exception):
    """Ends the call once the transaction has been captured."""


class _FakeContractFunction:
    def build_transaction(self, tx: dict[str, object]) -> dict[str, object]:
        # web3 echoes the caller's fields back and adds its own.
        return {**tx, "to": "0xpool", "data": "0xdeadbeef", "value": 0}


class _FakeFunctions:
    def recordBloom(self, *args: object) -> _FakeContractFunction:  # noqa: N802
        del args
        return _FakeContractFunction()

    def bloomRecorded(self, serial: int) -> object:  # noqa: N802
        del serial
        return _FakeCall(False)


class _FakeCall:
    def __init__(self, value: object) -> None:
        self._value = value

    def call(self) -> object:
        return self._value


class _FakeEth:
    max_priority_fee = 2_000_000_000

    def get_block(self, _which: str) -> dict[str, int]:
        return {"baseFeePerGas": 30_000_000_000}

    def get_transaction_count(self, _address: str) -> int:
        return 7

    def contract(self, **_kwargs: object) -> object:
        raise NotImplementedError


class _FakeWeb3:
    def __init__(self) -> None:
        self.eth = _FakeEth()


def test_the_sender_is_stripped_before_signing() -> None:
    # eth_account's RLP encoder rejects a 'from' key -- the sender is recovered from
    # the signature, not carried in the payload -- and fails with the unhelpful
    # "Unknown kwargs: ['from']". web3 puts it there because build_transaction echoes
    # back whatever it was given, so it has to be removed on the way out. The anchor
    # path already did this; the bloom path was written by copying that code and
    # dropping the one line, which cost a real burn on Amoy.
    from app.chain.bloom import ClaimPoolWriter

    signer = _RecordingSigner()
    writer = ClaimPoolWriter.__new__(ClaimPoolWriter)
    writer._web3 = _FakeWeb3()  # type: ignore[attr-defined]
    writer._signer = signer  # type: ignore[attr-defined]
    writer._chain_id = 80002  # type: ignore[attr-defined]
    writer._gas_limit = 300_000  # type: ignore[attr-defined]
    writer._contract = type("C", (), {"functions": _FakeFunctions()})()  # type: ignore[attr-defined]

    with pytest.raises(_StopHere):
        writer.record_bloom(2, "RARE", 92)

    assert "from" not in signer.seen
    assert signer.seen["nonce"] == 7
    assert signer.seen["chainId"] == 80002

