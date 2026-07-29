"""Tests for :mod:`app.chain.anchor_row` — the ``part = 8`` row, byte for byte.

``docs/CODEC.md`` §4.4 is normative. The current row is **version 0x02**: a 76-byte
payload with fixed offsets carrying the *full* 32-byte transaction and card hashes,
Z85 to 95 characters, ``id = serial*16 + 8``, ``value = -(serial*16 + 8)``,
``tag = psc.<serial>.8``. These tests reconstruct the expected bytes by hand from the
spec table and assert equality, exercise the decoder against both the 0x02 and the
legacy 0x01 layouts, and pin a vector taken from a real Anvil mint receipt.
"""

from __future__ import annotations

import struct

import pytest

from app.chain.anchor_row import (
    AMOY_EXPLORER_TX_BASE,
    ANCHOR_MAGIC,
    ANCHOR_PART,
    ANCHOR_ROW_CHARS,
    ANCHOR_VERSION,
    ANCHOR_VERSION_LEGACY,
    AnchorResult,
    ChainAnchor,
    build_anchor_row,
    build_anchor_row_from_result,
    decode_anchor_payload,
    decode_anchor_row,
    encode_anchor_payload,
    try_decode_anchor_row,
)
from app.chain.errors import AnchorRowError
from app.codec.keccak import keccak256
from app.codec.z85 import z85_decode, z85_encode

_TX = bytes.fromhex("deadbeefcafef00d" + "aa" * 24)  # 32-byte tx hash
_CARD = bytes.fromhex("0123456789abcdef" + "bb" * 24)  # 32-byte card hash


def _expected_payload_v2(serial: int, block: int, token: int) -> bytes:
    """Rebuild the 76 spec bytes (version 0x02) independently of the code (§4.4)."""
    out = bytearray()
    out.append(0x41)  # magic 'A'
    out.append(0x02)  # version
    out += struct.pack("<H", serial)  # serial u16 LE
    out += _TX  # full 32-byte tx hash
    out += struct.pack("<I", block)  # block u32 LE
    out += struct.pack("<I", token)  # tokenId u32 LE
    out += _CARD  # full 32-byte card hash
    assert len(out) == 76
    return bytes(out)


def _expected_payload_v1(serial: int, block: int, token: int) -> bytes:
    """Rebuild the 28 spec bytes of the legacy 0x01 layout (8-byte hash prefixes)."""
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
        assert payload == _expected_payload_v2(42, 15_000_000, 42)

    def test_field_offsets(self) -> None:
        payload = encode_anchor_payload(1, _TX, 0x00BC614E, 7, _CARD)
        assert payload[0] == ANCHOR_MAGIC == 0x41
        assert payload[1] == ANCHOR_VERSION == 0x02
        assert struct.unpack_from("<H", payload, 2)[0] == 1
        assert payload[4:36] == _TX  # the FULL tx hash, not a prefix
        assert struct.unpack_from("<I", payload, 36)[0] == 0x00BC614E
        assert struct.unpack_from("<I", payload, 40)[0] == 7
        assert payload[44:76] == _CARD  # the FULL card hash

    def test_length_is_76(self) -> None:
        assert len(encode_anchor_payload(1, _TX, 1, 1, _CARD)) == 76

    def test_hashes_are_not_truncated(self) -> None:
        # The whole reason for 0x02: a full hash a block explorer can address.
        payload = encode_anchor_payload(1, _TX, 1, 1, _CARD)
        assert _TX in payload
        assert _CARD in payload

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
            encode_anchor_payload(1, b"\x00" * 31, 1, 1, _CARD)

    def test_short_card_hash_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="card hash"):
            encode_anchor_payload(1, _TX, 1, 1, b"\x00" * 31)

    def test_unknown_version_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="unknown anchor version"):
            encode_anchor_payload(1, _TX, 1, 1, _CARD, version=0x09)


class TestEncodeLegacyV1:
    def test_v1_matches_spec_byte_for_byte(self) -> None:
        payload = encode_anchor_payload(
            42, _TX, 15_000_000, 42, _CARD, version=ANCHOR_VERSION_LEGACY
        )
        assert payload == _expected_payload_v1(42, 15_000_000, 42)

    def test_v1_length_is_28(self) -> None:
        assert len(encode_anchor_payload(1, _TX, 1, 1, _CARD, version=1)) == 28

    def test_v1_accepts_eight_byte_hashes(self) -> None:
        payload = encode_anchor_payload(1, b"\x11" * 8, 1, 1, b"\x22" * 8, version=1)
        assert payload[4:12] == b"\x11" * 8
        assert payload[20:28] == b"\x22" * 8


class TestBuildAnchorRow:
    def test_row_addressing_and_content(self) -> None:
        serial = 137
        row = build_anchor_row(serial, _TX, 9_000_000, serial, _CARD)
        assert row.id == serial * 16 + ANCHOR_PART
        assert row.value == -(serial * 16 + ANCHOR_PART)
        assert row.tag == f"psc.{serial}.8"
        assert len(row.content) == ANCHOR_ROW_CHARS == 95
        # Content decodes back to exactly the 76 spec bytes.
        assert z85_decode(row.content) == _expected_payload_v2(serial, 9_000_000, serial)

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


class TestDecodeAnchorRow:
    def test_round_trips_v2(self) -> None:
        row = build_anchor_row(42, _TX, 456_789, 123, _CARD)
        anchor = decode_anchor_row(row.content)
        assert anchor == ChainAnchor(
            version=0x02,
            serial=42,
            token_id=123,
            block_number=456_789,
            tx_hash=_TX,
            card_hash=_CARD,
        )
        assert anchor.full_hashes is True
        assert anchor.tx_hash_hex == "0x" + _TX.hex()
        assert anchor.card_hash_hex == "0x" + _CARD.hex()
        assert anchor.explorer_url == AMOY_EXPLORER_TX_BASE + "0x" + _TX.hex()

    def test_round_trips_v1_legacy(self) -> None:
        row = build_anchor_row(42, _TX, 456_789, 123, _CARD, version=ANCHOR_VERSION_LEGACY)
        anchor = decode_anchor_row(row.content)
        assert anchor.version == 0x01
        assert anchor.serial == 42
        assert anchor.token_id == 123
        assert anchor.block_number == 456_789
        assert anchor.tx_hash == _TX[:8]  # only the prefix survived
        assert anchor.card_hash == _CARD[:8]
        assert anchor.full_hashes is False
        assert anchor.explorer_url is None  # a prefix cannot address a block explorer

    def test_decode_payload_directly(self) -> None:
        anchor = decode_anchor_payload(_expected_payload_v2(7, 99, 7))
        assert anchor.version == 2
        assert anchor.serial == 7
        assert anchor.block_number == 99
        assert anchor.token_id == 7
        assert anchor.tx_hash == _TX

    def test_bad_magic_raises(self) -> None:
        payload = bytearray(_expected_payload_v2(1, 5, 9))
        payload[0] = 0x42  # not 'A'
        with pytest.raises(AnchorRowError, match="magic"):
            decode_anchor_row(z85_encode(bytes(payload)))

    def test_unknown_version_raises(self) -> None:
        payload = bytearray(_expected_payload_v2(1, 5, 9))
        payload[1] = 0x09
        with pytest.raises(AnchorRowError, match="unknown anchor version"):
            decode_anchor_row(z85_encode(bytes(payload)))

    def test_length_mismatch_raises(self) -> None:
        # A 28-byte v1-length body that claims to be version 0x02.
        payload = bytearray(_expected_payload_v1(1, 5, 9))
        payload[1] = 0x02
        with pytest.raises(AnchorRowError, match="expected 76"):
            decode_anchor_row(z85_encode(bytes(payload)))

    def test_bad_z85_raises(self) -> None:
        with pytest.raises(AnchorRowError, match="Z85"):
            decode_anchor_row("abc")

    def test_expected_serial_match_ok(self) -> None:
        row = build_anchor_row(77, _TX, 1, 77, _CARD)
        assert decode_anchor_row(row.content, expected_serial=77).serial == 77

    def test_expected_serial_mismatch_raises(self) -> None:
        row = build_anchor_row(42, _TX, 1, 42, _CARD)
        with pytest.raises(AnchorRowError, match="does not match expected"):
            decode_anchor_row(row.content, expected_serial=99)

    def test_try_decode_returns_none_on_bad_content(self) -> None:
        assert try_decode_anchor_row("abc") is None
        assert try_decode_anchor_row("") is None

    def test_try_decode_returns_none_on_serial_mismatch(self) -> None:
        row = build_anchor_row(42, _TX, 1, 42, _CARD)
        assert try_decode_anchor_row(row.content, expected_serial=99) is None

    def test_try_decode_returns_anchor_on_good_content(self) -> None:
        row = build_anchor_row(42, _TX, 1, 42, _CARD)
        anchor = try_decode_anchor_row(row.content)
        assert anchor is not None and anchor.serial == 42


class TestRealAnvilVector:
    # Captured from a real mintCard on a local Anvil node (chainId 31337): the Python
    # Anchorer signed and broadcast, the receipt landed in block 6 as tokenId 1.
    _SERIAL = 1
    _TX_HASH = bytes.fromhex("c8e2d173661c1c739beb3feaca317a4be05d1cb5a43d0ba8fa034af7ddfc4b96")
    _BLOCK = 6
    _TOKEN_ID = 1
    _CARD_HASH = keccak256(b"PSC-1 stream for serial 1")

    def _result(self) -> AnchorResult:
        return AnchorResult(
            serial=self._SERIAL,
            tx_hash=self._TX_HASH,
            block_number=self._BLOCK,
            token_id=self._TOKEN_ID,
            card_hash=self._CARD_HASH,
        )

    def test_row_addressing(self) -> None:
        row = build_anchor_row_from_result(self._result())
        assert row.id == self._SERIAL * 16 + 8 == 24
        assert row.value == -24
        assert row.tag == "psc.1.8"
        assert len(row.content) == 95

    def test_round_trip_matches_the_receipt(self) -> None:
        row = build_anchor_row_from_result(self._result())
        anchor = decode_anchor_row(row.content, expected_serial=1)
        assert anchor.version == 0x02
        assert anchor.token_id == 1
        assert anchor.block_number == 6
        assert anchor.tx_hash == self._TX_HASH
        assert anchor.tx_hash_hex == "0x" + self._TX_HASH.hex()
        assert anchor.card_hash == self._CARD_HASH
        assert anchor.explorer_url == (
            "https://amoy.polygonscan.com/tx/"
            "0xc8e2d173661c1c739beb3feaca317a4be05d1cb5a43d0ba8fa034af7ddfc4b96"
        )

    def test_payload_bytes_are_reconstructible_by_hand(self) -> None:
        row = build_anchor_row_from_result(self._result())
        expected = bytearray()
        expected.append(0x41)
        expected.append(0x02)
        expected += struct.pack("<H", 1)
        expected += self._TX_HASH
        expected += struct.pack("<I", 6)
        expected += struct.pack("<I", 1)
        expected += self._CARD_HASH
        assert len(expected) == 76
        assert z85_decode(row.content) == bytes(expected)
