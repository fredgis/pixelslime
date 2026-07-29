"""Property-based tests: thousands of random valid cards must round-trip exactly."""

from __future__ import annotations

from _codec_helpers import cards
from hypothesis import given, settings
from hypothesis import strategies as st

from app.codec import Card, card_hash, decode, encode, encode_stream
from app.codec.z85 import ALPHABET

_ALPHABET_SET = set(ALPHABET)


@given(card=cards())
@settings(max_examples=5000, deadline=None)
def test_encode_decode_roundtrip_preserves_every_field(card: Card) -> None:
    decoded = decode(encode(card))
    assert decoded == card
    # Spell out a few fields so a failure names the culprit, not just "!=".
    assert decoded.name == card.name
    assert decoded.serial == card.serial
    assert decoded.rarity == card.rarity
    assert decoded.type == card.type
    assert decoded.shiny == card.shiny
    assert decoded.flags == card.flags
    assert decoded.companion_id == card.companion_id
    assert decoded.art_sha == card.art_sha
    assert decoded.mint_day == card.mint_day


@given(card=cards())
@settings(max_examples=5000, deadline=None)
def test_every_emitted_content_is_asmdb_safe(card: Card) -> None:
    rows = encode(card)
    assert 1 <= len(rows) <= 4
    for row in rows:
        encoded = row.content.encode("utf-8")
        assert len(encoded) <= 175
        assert not ({"\x00", "\r", "\n"} & set(row.content))
        assert set(row.content) <= _ALPHABET_SET


@given(card=cards())
@settings(max_examples=1000, deadline=None)
def test_encode_is_deterministic(card: Card) -> None:
    assert encode(card) == encode(card)
    assert encode_stream(card) == encode_stream(card)
    assert card_hash(card) == card_hash(card)


@given(card=cards(), data=st.data())
@settings(max_examples=1000, deadline=None)
def test_decode_is_order_insensitive(card: Card, data: st.DataObject) -> None:
    rows = encode(card)
    shuffled = data.draw(st.permutations(rows))
    assert decode(list(shuffled)) == card


@given(card=cards())
@settings(max_examples=2000, deadline=None)
def test_value_signs_separate_headers_from_continuations(card: Card) -> None:
    rows = encode(card)
    assert rows[0].value > 0  # header carries a positive mint date
    for row in rows[1:]:
        assert row.value < 0  # continuations are always negative
