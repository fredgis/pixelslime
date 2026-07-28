"""Tests for CRC-16/CCITT-FALSE."""

from __future__ import annotations

from app.codec.crc import crc16_ccitt_false


def test_check_value() -> None:
    # The catalogue check value for CRC-16/CCITT-FALSE.
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_empty_is_init_value() -> None:
    # With no input the result is just the initial register value.
    assert crc16_ccitt_false(b"") == 0xFFFF


def test_single_bit_change_changes_crc() -> None:
    assert crc16_ccitt_false(b"A") != crc16_ccitt_false(b"B")


def test_deterministic() -> None:
    payload = bytes(range(256)) * 3
    assert crc16_ccitt_false(payload) == crc16_ccitt_false(payload)


def test_result_is_16_bit() -> None:
    for payload in (b"", b"x", b"123456789", bytes(range(256))):
        assert 0 <= crc16_ccitt_false(payload) <= 0xFFFF
