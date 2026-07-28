"""Tests for the pure-Python keccak256 (Ethereum variant)."""

from __future__ import annotations

import hashlib

from app.codec.keccak import keccak256

# Known-answer vectors for Ethereum keccak256 (0x01 domain padding).
_VECTORS = {
    b"": "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
    b"abc": "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45",
    b"The quick brown fox jumps over the lazy dog": (
        "4d741b6f1eb29cb2a9b9911c82f56fa8d73b04959d3d9d222895df6c0b28aa15"
    ),
}


def test_empty_string_known_answer() -> None:
    # The exact anchor the spec calls out; if this drifts the on-chain hash breaks.
    assert (
        keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    )


def test_known_answers() -> None:
    for message, expected in _VECTORS.items():
        assert keccak256(message).hex() == expected


def test_digest_is_32_bytes() -> None:
    assert len(keccak256(b"anything")) == 32


def test_is_not_sha3_256() -> None:
    # keccak256 and NIST SHA3-256 share the permutation but differ in padding;
    # this guards against a silent hashlib.sha3_256 substitution.
    assert keccak256(b"") != hashlib.sha3_256(b"").digest()
    assert keccak256(b"abc") != hashlib.sha3_256(b"abc").digest()


def test_multiblock_input() -> None:
    # Longer than the 136-byte rate to exercise multiple absorb rounds.
    message = b"pixelslime" * 100
    assert len(keccak256(message)) == 32
    assert keccak256(message) == keccak256(message)
