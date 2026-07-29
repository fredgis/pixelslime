"""Behavioural tests for the public PSC-1 codec API."""

from __future__ import annotations

import datetime as dt

import pytest
from _codec_helpers import FIXTURE_NAMES, load_card

from app.codec import (
    Card,
    CodecError,
    CompanionError,
    CrcError,
    FieldLimitError,
    HeaderError,
    Row,
    RowError,
    StreamTooLargeError,
    card_hash,
    decode,
    encode,
    encode_stream,
)
from app.codec.codec import EPOCH, MAX_STREAM, _mint_value, _split_rows
from app.codec.z85 import ALPHABET, z85_encode

# ── Frozen format vectors. If the byte layout drifts, these break loudly. ──────
_STREAM_HEX = {
    "mochibo": (
        "5001010034000c03180184031c37415f0101030704021700d000000000005c39"
        "83b6e5e5c96b90c923d747f26416e7f238731200"
    ),
    "worstcase-unseen": (
        "50018403b7002fa49f01d40858475d402a0104130b06060090011a2b3c4d77b1"
        "3597310e802014438f8207500fe1e2e0e2e005104c2012301f71f0f4b6106792"
        "cf4f685fcbe66a778a6557336074fd586cfd06665de5b09e410bf3be2f3b853d"
        "82afdcce1704a74d098824e37422d4a03c6d4735e1020c12644a1dab184ecdbe"
        "583f6702b744e8b213ffb0e1e412ce9ee711f35192ebb3eaeef1897dfd6e5b1a"
        "210bd422720e133e4223b5468de2c56243c19e2c2cf301"
    ),
    "worstcase-maxlen": (
        "5001ffffcd0064fdffffffff64646464ffff05ffffff0f00ffffffffffff10a5"
        "25963b1683201045978294295c418a74e9d3e4e4d8893128203f9df0597d1e66"
        "01cccc7bf3e10eb5e4f04d44f640319ebd8a717e699b17084f817357a8a53d10"
        "fa5110dcf60a17652ecdcedcf90514be9d7f47754ec388e6bffdc30fe7ec91d6"
        "ac70e320f05eab18ad64c32aeb2811de698d06ab11a95b2c883048068c889f5e"
        "9c4eed1e539ea14a9201c09769362b901f7c62df672727cd9e29df3073830a3d"
        "8ad93a994b85612246cff9e507"
    ),
}
_CARD_HASH = {
    "mochibo": "718e809df90bbce66bf7bac60feff91edc4b97653771834555a037d58e680a1c",
    "worstcase-unseen": "e360a554098d61252d18ea19a0ef4a7a8ef50f7460065b7ac041880e59f5cde2",
    "worstcase-maxlen": "e08674acc53a79db3bf9d0c17dbd582b234335f347a24cfabe13951b7aa72f08",
}
_EXPECTED_ROWS = {"mochibo": 1, "worstcase-unseen": 2, "worstcase-maxlen": 2}


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_roundtrips_every_field(name: str) -> None:
    card = load_card(name)
    assert decode(encode(card)) == card


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_row_count(name: str) -> None:
    assert len(encode(load_card(name))) == _EXPECTED_ROWS[name]


def test_mochibo_fits_in_at_most_two_rows() -> None:
    assert len(encode(load_card("mochibo"))) <= 2


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_stream_regression_vector(name: str) -> None:
    assert encode_stream(load_card(name)).hex() == _STREAM_HEX[name]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_card_hash_regression_vector(name: str) -> None:
    assert card_hash(load_card(name)).hex() == _CARD_HASH[name]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_card_hash_is_keccak_of_stream(name: str) -> None:
    from app.codec.keccak import keccak256

    card = load_card(name)
    digest = card_hash(card)
    assert len(digest) == 32
    assert digest == keccak256(encode_stream(card))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_encode_is_deterministic_100_calls(name: str) -> None:
    card = load_card(name)
    first_rows = encode(card)
    first_stream = encode_stream(card)
    first_hash = card_hash(card)
    for _ in range(100):
        assert encode(card) == first_rows
        assert encode_stream(card) == first_stream
        assert card_hash(card) == first_hash


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_value_sign_convention(name: str) -> None:
    card = load_card(name)
    rows = encode(card)
    expected_date = EPOCH + dt.timedelta(days=card.mint_day)
    yyyymmdd = expected_date.year * 10000 + expected_date.month * 100 + expected_date.day
    assert rows[0].value == yyyymmdd > 0
    for part, row in enumerate(rows[1:], start=1):
        assert row.value == -(card.serial * 16 + part) < 0


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_row_id_and_tag_addressing(name: str) -> None:
    card = load_card(name)
    rows = encode(card)
    for part, row in enumerate(rows):
        assert row.id == card.serial * 16 + part
        assert row.tag == f"psc.{card.serial}.{part}"
        assert len(row.tag.encode("utf-8")) <= 39
        assert " " not in row.tag


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_content_is_asmdb_safe(name: str) -> None:
    rows = encode(load_card(name))
    assert len(rows) <= 4
    for row in rows:
        encoded = row.content.encode("utf-8")
        assert len(encoded) <= 175
        assert b"\x00" not in encoded
        assert b"\r" not in encoded
        assert b"\n" not in encoded
        assert set(row.content) <= set(ALPHABET)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_decode_is_order_insensitive(name: str) -> None:
    card = load_card(name)
    rows = encode(card)
    assert decode(list(reversed(rows))) == card


def test_decode_ignores_unrelated_anchor_row() -> None:
    card = load_card("worstcase-unseen")
    rows = encode(card)
    anchor = Row(
        id=card.serial * 16 + 8,
        value=-(card.serial * 16 + 8),
        tag=f"psc.{card.serial}.8",
        content=z85_encode(b"anchor-ish"),
    )
    assert decode([*rows, anchor]) == card


def test_missing_continuation_row_raises() -> None:
    rows = encode(load_card("worstcase-unseen"))
    assert len(rows) == 2
    with pytest.raises(RowError):
        decode([rows[0]])  # drop the continuation


def test_missing_header_row_raises() -> None:
    rows = encode(load_card("worstcase-unseen"))
    with pytest.raises(RowError):
        decode([rows[1]])  # only the continuation, no part 0


def test_empty_rows_raises() -> None:
    with pytest.raises(RowError):
        decode([])


def test_conflicting_rows_same_id_raises() -> None:
    rows = encode(load_card("mochibo"))
    clashing = rows[0].model_copy(update={"content": z85_encode(b"different")})
    with pytest.raises(RowError):
        decode([rows[0], clashing])


def test_rows_from_two_cards_raises() -> None:
    with pytest.raises(RowError):
        decode([encode(load_card("mochibo"))[0], encode(load_card("worstcase-unseen"))[0]])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_no_single_character_corruption_is_silently_accepted(name: str) -> None:
    """Every single-character change to any content must be rejected, never
    decoded into a plausible wrong card. This subsumes the CRC guarantee."""
    card = load_card(name)
    rows = encode(card)
    saw_crc_error = False
    for index, row in enumerate(rows):
        for pos in range(len(row.content)):
            original = row.content[pos]
            replacement = ALPHABET[(ALPHABET.index(original) + 1) % len(ALPHABET)]
            mutated = row.content[:pos] + replacement + row.content[pos + 1 :]
            corrupted = [*rows]
            corrupted[index] = row.model_copy(update={"content": mutated})
            with pytest.raises(CodecError) as excinfo:
                decode(corrupted)
            saw_crc_error = saw_crc_error or isinstance(excinfo.value, CrcError)
    assert saw_crc_error  # the CRC path must actually fire for some corruption


def test_crc_detects_body_byte_flip() -> None:
    card = load_card("worstcase-maxlen")
    stream = bytearray(encode_stream(card))
    stream[-1] ^= 0x01  # flip a bit in the last body byte
    corrupted_rows = _split_rows(bytes(stream), serial=card.serial, mint_day=card.mint_day)
    with pytest.raises(CrcError):
        decode(corrupted_rows)


def test_reserved_flag_bits_rejected_on_decode() -> None:
    card = load_card("mochibo")
    stream = bytearray(encode_stream(card))
    stream[23] |= 1 << 3  # flags bit 11 (reserved) lives in the high byte
    rows = _split_rows(bytes(stream), serial=card.serial, mint_day=card.mint_day)
    with pytest.raises(HeaderError):
        decode(rows)


@pytest.mark.parametrize("companion_id", range(64))
def test_companion_id_roundtrips_all_64_values(companion_id: int) -> None:
    base = load_card("mochibo")  # mochibo has has_companion == True
    assert base.flags.has_companion is True
    card = base.model_copy(update={"companion_id": companion_id})
    decoded = decode(encode(card))
    assert decoded.companion_id == companion_id
    assert decoded == card


def test_companion_id_zero_without_flag_is_valid() -> None:
    card = load_card("worstcase-unseen")  # has_companion False, companion_id defaults to 0
    assert card.flags.has_companion is False
    assert card.companion_id == 0
    assert decode(encode(card)).companion_id == 0


def test_companion_id_set_without_flag_raises() -> None:
    data = load_card("mochibo").model_dump()
    data["flags"] = {**data["flags"], "has_companion": False}
    data["companion_id"] = 7
    with pytest.raises(CompanionError):
        Card.model_validate(data)


def test_companion_error_is_a_codec_error() -> None:
    assert issubclass(CompanionError, CodecError)


def test_companion_id_out_of_range_rejected() -> None:
    base = load_card("mochibo").model_dump()
    for bad in (-1, 64):
        with pytest.raises(ValueError):
            Card.model_validate({**base, "companion_id": bad})


def test_over_long_char_field_raises_not_truncates() -> None:
    card = load_card("mochibo")
    too_long = card.model_copy(update={"name": "N" * 19})  # 19 > 18-char limit
    with pytest.raises(FieldLimitError):
        encode(too_long)


def test_over_long_utf8_byte_field_raises() -> None:
    # 13 three-byte characters = 39 bytes: within the 18-char limit but over the
    # 36-byte limit, so a schema-valid card is still rejected at encode time.
    card = Card.model_validate({**load_card("mochibo").model_dump(), "name": "中" * 13})
    assert len(card.name) == 13
    assert len(card.name.encode("utf-8")) == 39
    with pytest.raises(FieldLimitError):
        encode(card)


def test_forbidden_control_byte_in_field_raises() -> None:
    card = load_card("mochibo").model_copy(update={"quote": "a\x1fb"})
    with pytest.raises(FieldLimitError):
        encode(card)


def test_split_rows_rejects_over_ceiling_stream() -> None:
    assert len(_split_rows(b"\x00" * MAX_STREAM, serial=1, mint_day=0)) == 4
    with pytest.raises(StreamTooLargeError):
        _split_rows(b"\x00" * (MAX_STREAM + 1), serial=1, mint_day=0)


def test_mint_value_matches_calendar() -> None:
    assert _mint_value(0) == 20260101
    assert _mint_value(208) == 20260728  # mochibo's mint day
