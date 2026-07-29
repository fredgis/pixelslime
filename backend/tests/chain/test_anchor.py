"""Tests for :mod:`app.chain.anchor` — the idempotent on-chain mint path.

The headline guarantee is that a serial is minted **at most once**: if the contract
already reports a ``cardHash`` for it, no transaction is broadcast. These use the
``_chain_helpers.FakeNode`` to record sends, so the assertions are about behaviour
(did we send? how many times?) rather than any live chain.
"""

from __future__ import annotations

import pytest
from _chain_helpers import KV_ADDRESS, SAMPLE_CARD_HASH, FakeNode, FakeSigner

from app.chain.anchor import Anchorer
from app.chain.anchor_row import build_anchor_row_from_result
from app.chain.errors import AnchorError

_URI = "/api/nft/42"


def _anchorer(node: FakeNode) -> Anchorer:
    return Anchorer(node, node.card_address, FakeSigner(KV_ADDRESS), chain_id=80002)


class TestAnchorIdempotency:
    def test_fresh_mint_sends_exactly_one_transaction(self) -> None:
        node = FakeNode()
        anchorer = _anchorer(node)
        receipt = anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        assert len(node.sent) == 1
        assert receipt.already_minted is False
        assert receipt.tx_hash == node.tx_hash
        assert receipt.block_number == node.block_number
        assert receipt.token_id == 42

    def test_already_minted_sends_nothing(self) -> None:
        node = FakeNode()
        node.mark_minted(42, SAMPLE_CARD_HASH)
        anchorer = _anchorer(node)
        receipt = anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        assert node.sent == []  # not a single transaction broadcast
        assert receipt.already_minted is True
        assert receipt.tx_hash is None
        assert receipt.block_number is None

    def test_second_call_after_first_is_a_noop(self) -> None:
        # Simulate a re-run: the first anchor marks the serial minted, the second
        # must observe it and skip. This is the batch-retry safety property.
        node = FakeNode()
        anchorer = _anchorer(node)
        anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        node.mark_minted(42, SAMPLE_CARD_HASH)  # the mint has now landed
        anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        assert len(node.sent) == 1  # still just the one send


class TestAnchorFlow:
    def test_is_minted_probe(self) -> None:
        node = FakeNode()
        anchorer = _anchorer(node)
        assert anchorer.is_minted(42) is False
        node.mark_minted(42, SAMPLE_CARD_HASH)
        assert anchorer.is_minted(42) is True

    def test_reverted_receipt_raises(self) -> None:
        node = FakeNode()
        node.receipt_status = 0  # the mint reverted on-chain
        anchorer = _anchorer(node)
        with pytest.raises(AnchorError, match="reverted"):
            anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)

    def test_bad_hash_length_raises(self) -> None:
        node = FakeNode()
        anchorer = _anchorer(node)
        with pytest.raises(AnchorError, match="32 bytes"):
            anchorer.anchor(42, b"\x00" * 8, _URI)

    def test_receipt_feeds_the_anchor_row(self) -> None:
        node = FakeNode()
        anchorer = _anchorer(node)
        receipt = anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        row = build_anchor_row_from_result(receipt.to_anchor_result())
        assert row.tag == "psc.42.8"
        assert row.id == 42 * 16 + 8

    def test_noop_receipt_has_no_anchor_result(self) -> None:
        node = FakeNode()
        node.mark_minted(42, SAMPLE_CARD_HASH)
        anchorer = _anchorer(node)
        receipt = anchorer.anchor(42, SAMPLE_CARD_HASH, _URI)
        with pytest.raises(AnchorError, match="already minted"):
            receipt.to_anchor_result()
