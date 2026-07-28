"""Tests for the 32-byte PSC-1 header: layout, bitfields and validation."""

from __future__ import annotations

import struct

import pytest

from app.codec.errors import HeaderError
from app.codec.header import HEADER_LEN, MAGIC, VERSION, Header


def _base_header(**overrides: object) -> Header:
    """A fully-populated, in-range header; override any field per test."""
    defaults: dict[str, object] = {
        "serial": 900,
        "total_len": 183,
        "level": 47,
        "rarity": 4,
        "type_id": 4,
        "shiny": True,
        "height_mm": 415,
        "weight_g": 2260,
        "strength": 88,
        "endurance": 71,
        "agility": 93,
        "happiness": 64,
        "art_id": 42,
        "style_id": 1,
        "frame_id": 4,
        "background_id": 19,
        "biome_id": 11,
        "mood_id": 6,
        "has_companion": False,
        "has_accessory": True,
        "verified": True,
        "on_chain": False,
        "seed": False,
        "mint_day": 400,
        "art_sha": bytes.fromhex("1a2b3c4d"),
    }
    defaults.update(overrides)
    return Header(**defaults)  # type: ignore[arg-type]


def test_header_packs_to_exactly_32_bytes() -> None:
    assert len(_base_header().pack()) == HEADER_LEN
    assert len(_base_header().prefix()) == HEADER_LEN - 2


def test_roundtrip_preserves_every_field() -> None:
    header = _base_header()
    packed = header.pack()
    back = Header.unpack(packed)
    assert back == header


def test_little_endian_field_positions() -> None:
    header = _base_header(serial=0x1234, total_len=0x00C8, height_mm=0x0402, mint_day=0x0190)
    raw = header.prefix()
    assert raw[0] == MAGIC
    assert raw[1] == VERSION
    assert raw[2:4] == b"\x34\x12"  # serial, little-endian
    assert raw[4:6] == b"\xc8\x00"  # total_len, little-endian
    assert raw[8:10] == b"\x02\x04"  # height_mm, little-endian
    assert raw[24:26] == b"\x90\x01"  # mint_day, little-endian
    assert raw[26:30] == bytes.fromhex("1a2b3c4d")  # art_sha, verbatim order


@pytest.mark.parametrize("rarity", range(6))
@pytest.mark.parametrize("type_id", range(16))
@pytest.mark.parametrize("shiny", [False, True])
def test_bitfield_roundtrip_exhaustive(rarity: int, type_id: int, shiny: bool) -> None:
    header = _base_header(rarity=rarity, type_id=type_id, shiny=shiny)
    frt = header.prefix()[7]
    # Bit layout per §3.2: rarity 0..2, type 3..6, shiny 7.
    assert frt & 0x07 == rarity
    assert (frt >> 3) & 0x0F == type_id
    assert (frt >> 7) & 0x01 == int(shiny)
    back = Header.unpack(header.pack())
    assert (back.rarity, back.type_id, back.shiny) == (rarity, type_id, shiny)


@pytest.mark.parametrize(
    ("field", "expected_bit"),
    [
        ("has_companion", 0),
        ("has_accessory", 1),
        ("verified", 2),
        ("on_chain", 3),
        ("seed", 4),
    ],
)
def test_flags_word_bit_positions(field: str, expected_bit: int) -> None:
    clear = _base_header(
        has_companion=False,
        has_accessory=False,
        verified=False,
        on_chain=False,
        seed=False,
    )
    header = _base_header(
        **{  # type: ignore[arg-type]
            "has_companion": False,
            "has_accessory": False,
            "verified": False,
            "on_chain": False,
            "seed": False,
            field: True,
        }
    )
    (word,) = struct.unpack("<H", header.prefix()[22:24])
    (clear_word,) = struct.unpack("<H", clear.prefix()[22:24])
    assert clear_word == 0
    assert word == (1 << expected_bit)


def test_unpack_rejects_bad_magic() -> None:
    raw = bytearray(_base_header().pack())
    raw[0] = 0x41  # 'A'
    with pytest.raises(HeaderError):
        Header.unpack(bytes(raw))


def test_unpack_rejects_bad_version() -> None:
    raw = bytearray(_base_header().pack())
    raw[1] = 0x02
    with pytest.raises(HeaderError):
        Header.unpack(bytes(raw))


def test_unpack_rejects_reserved_flag_bits() -> None:
    raw = bytearray(_base_header().pack())
    # Set flags bit 5 (reserved) — must be rejected in version 1.
    word = struct.unpack("<H", bytes(raw[22:24]))[0] | (1 << 5)
    raw[22:24] = struct.pack("<H", word)
    with pytest.raises(HeaderError):
        Header.unpack(bytes(raw))


def test_unpack_rejects_undefined_rarity() -> None:
    raw = bytearray(_base_header().pack())
    raw[7] = (raw[7] & ~0x07) | 0x06  # rarity ordinal 6 is undefined
    with pytest.raises(HeaderError):
        Header.unpack(bytes(raw))


def test_unpack_rejects_short_buffer() -> None:
    with pytest.raises(HeaderError):
        Header.unpack(b"\x50\x01")


def test_prefix_rejects_bad_art_sha_length() -> None:
    with pytest.raises(HeaderError):
        _base_header(art_sha=b"\x00\x00").prefix()


def test_serial_out_of_range_raises() -> None:
    with pytest.raises(HeaderError):
        _base_header(serial=70000).prefix()  # exceeds u16
