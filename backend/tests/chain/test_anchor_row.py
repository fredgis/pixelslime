"""Tests for :mod:`app.chain.anchor_row` — the ``part = 8`` row, byte for byte.

``docs/CODEC.md`` §4.4 is normative: a 28-byte payload with fixed offsets, Z85 to
35 characters, ``id = serial*16 + 8``, ``value = -(serial*16 + 8)``,
``tag = psc.<serial>.8``. These tests reconstruct the expected bytes by hand from
the spec table and assert equality, then check the row addressing and the loud
failures on out-of-range fields.
"""

from __future__ import annotations

import struct

import pytest

from app.chain.anchor_row import (
    ANCHOR_MAGIC,
    ANCHOR_PART,
    ANCHOR_VERSION,
    AnchorResult,
    build_anchor_row,
    build_anchor_row_from_result,
    encode_anchor_payload,
)
from app.chain.errors import AnchorRowError
from app.codec.z85 import z85_decode, z85_encode

_TX = bytes.fromhex("deadbeefcafef00d" + "aa" * 24)  # 32-byte tx hash
_CARD = bytes.fromhex("0123456789abcdef" + "bb" * 24)  # 32-byte card hash


def _expected_payload(serial: int, block: int, token: int) -> bytes:
    """Rebuild the 28 spec bytes independently of the implementation (§4.4)."""
    out = bytearray()
    out.append(0x41)  # magic 'A'
    out.append(0x01)  # version
    out += struct.pack("<H", serial)  # serial u16 LE
    out += _TX[:8]  # tx hash prefix
    out += struct.pack("<I", block)  # block u32 LE
    out += struct.pack("<I", token)  # tokenId u32 LE
    out += _CARD[:8]  # card hash prefix
    assert len(out) == 28
    return bytes(out)


class TestEncodeAnchorPayload:
    def test_matches_spec_byte_for_byte(self) -> None:
        payload = encode_anchor_payload(42, _TX, 15_000_000, 42, _CARD)
        assert payload == _expected_payload(42, 15_000_000, 42)

    def test_field_offsets(self) -> None:
        payload = encode_anchor_payload(1, _TX, 0x00BC614E, 7, _CARD)
        assert payload[0] == ANCHOR_MAGIC == 0x41
        assert payload[1] == ANCHOR_VERSION == 0x01
        assert struct.unpack_from("<H", payload, 2)[0] == 1
        assert payload[4:12] == _TX[:8]
        assert struct.unpack_from("<I", payload, 12)[0] == 0x00BC614E
        assert struct.unpack_from("<I", payload, 16)[0] == 7
        assert payload[20:28] == _CARD[:8]

    def test_length_is_28(self) -> None:
        assert len(encode_anchor_payload(1, _TX, 1, 1, _CARD)) == 28

    @pytest.mark.parametrize("serial", [0, 65_536, -1])
    def test_serial_out_of_range_raises(self, serial: int) -> None:
        with pytest.raises(AnchorRowError, match="serial"):
            encode_anchor_payload(serial, _TX, 1, 1, _CARD)

    def test_block_over_u32_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="block"):
            encode_anchor_payload(1, _TX, 2**32, 1, _CARD)

    def test_token_over_u32_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="tokenId"):
            encode_anchor_payload(1, _TX, 1, 2**32, _CARD)

    def test_short_tx_hash_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="tx hash"):
            encode_anchor_payload(1, b"\x00" * 7, 1, 1, _CARD)

    def test_short_card_hash_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="card hash"):
            encode_anchor_payload(1, _TX, 1, 1, b"\x00" * 7)


class TestBuildAnchorRow:
    def test_row_addressing_and_content(self) -> None:
        serial = 137
        row = build_anchor_row(serial, _TX, 9_000_000, serial, _CARD)
        assert row.id == serial * 16 + ANCHOR_PART
        assert row.value == -(serial * 16 + ANCHOR_PART)
        assert row.tag == f"psc.{serial}.8"
        assert len(row.content) == 35
        # Content decodes back to exactly the 28 spec bytes.
        assert z85_decode(row.content) == _expected_payload(serial, 9_000_000, serial)

    def test_content_is_z85_of_payload(self) -> None:
        payload = encode_anchor_payload(9, _TX, 5, 9, _CARD)
        row = build_anchor_row(9, _TX, 5, 9, _CARD)
        assert row.content == z85_encode(payload)

    def test_part_is_eight(self) -> None:
        assert ANCHOR_PART == 8
        row = build_anchor_row(1, _TX, 1, 1, _CARD)
        assert row.id % 16 == 8

    def test_from_result_matches_direct(self) -> None:
        result = AnchorResult(
            serial=88, tx_hash=_TX, block_number=12_345, token_id=88, card_hash=_CARD
        )
        assert build_anchor_row_from_result(result) == build_anchor_row(88, _TX, 12_345, 88, _CARD)

    def test_value_is_negative_so_it_escapes_range_queries(self) -> None:
        # A header RANGE query uses lo >= 0; the anchor row must never surface there.
        row = build_anchor_row(500, _TX, 1, 500, _CARD)
        assert row.value < 0
