"""Tests for the Z85 text envelope."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.codec.errors import Z85Error
from app.codec.z85 import ALPHABET, z85_decode, z85_encode

# The canonical ZeroMQ Z85 reference vector.
_HELLO_BYTES = bytes([0x86, 0x4F, 0xD2, 0x6F, 0xB5, 0x59, 0xF7, 0x5B])
_HELLO_TEXT = "HelloWorld"


def test_reference_vector() -> None:
    assert z85_encode(_HELLO_BYTES) == _HELLO_TEXT
    assert z85_decode(_HELLO_TEXT) == _HELLO_BYTES


def test_alphabet_is_85_unique_symbols() -> None:
    assert len(ALPHABET) == 85
    assert len(set(ALPHABET)) == 85
    for forbidden in ("\x00", "\r", "\n", "\\", " ", "\t", '"', "'"):
        assert forbidden not in ALPHABET


def test_capacity_140_bytes_is_175_chars() -> None:
    # This 140 -> 175 ratio is the whole reason a row holds 140 binary bytes.
    assert len(z85_encode(b"\x00" * 140)) == 175


@given(st.binary(min_size=0, max_size=600))
@settings(max_examples=1000)
def test_roundtrip_recovers_original_prefix(data: bytes) -> None:
    encoded = z85_encode(data)
    assert len(encoded) % 5 == 0
    decoded = z85_decode(encoded)
    # Z85 rounds up to a multiple of four bytes; the original is a prefix.
    assert decoded[: len(data)] == data
    assert len(decoded) == (len(data) + 3) // 4 * 4


@given(st.binary(min_size=0, max_size=200))
def test_encoded_is_pure_alphabet(data: bytes) -> None:
    assert set(z85_encode(data)) <= set(ALPHABET)


def test_reject_length_not_multiple_of_five() -> None:
    with pytest.raises(Z85Error):
        z85_decode("abcd")


def test_reject_character_outside_alphabet() -> None:
    with pytest.raises(Z85Error):
        z85_decode("abc d")  # space is not in the alphabet
    with pytest.raises(Z85Error):
        z85_decode("abc\x00d")


def test_reject_uint32_overflow() -> None:
    # "#####" decodes to 84*(85^4+85^3+85^2+85+1), far beyond 0xFFFFFFFF.
    with pytest.raises(Z85Error):
        z85_decode("#####")


def test_short_input_padding_roundtrip() -> None:
    encoded = z85_encode(b"\x01\x02\x03")
    assert len(encoded) == 5
    assert z85_decode(encoded) == b"\x01\x02\x03\x00"
