"""PSC-1 — the PixelSlime card codec (version 1).

Public surface, per ``docs/CODEC.md`` §6::

    encode(card)         -> list[Row]   # card -> ordered asmDB rows
    decode(rows)         -> Card        # rows -> card, order-insensitive
    encode_stream(card)  -> bytes       # the raw PSC-1 stream, pre-Z85
    card_hash(card)      -> bytes       # keccak256(encode_stream(card))

Everything raises a subclass of :class:`CodecError` on any violation; nothing is
ever silently truncated or defaulted.
"""

from __future__ import annotations

from .card import RARITIES, TYPES, Card, Flags, Rarity, Row, SlimeType
from .codec import card_hash, decode, encode, encode_stream
from .errors import (
    BodyError,
    CodecError,
    CrcError,
    DictionaryError,
    FieldLimitError,
    HeaderError,
    RowError,
    StreamTooLargeError,
    Z85Error,
)

__all__ = [
    "RARITIES",
    "TYPES",
    "BodyError",
    "Card",
    "CodecError",
    "CrcError",
    "DictionaryError",
    "FieldLimitError",
    "Flags",
    "HeaderError",
    "Rarity",
    "Row",
    "RowError",
    "SlimeType",
    "StreamTooLargeError",
    "Z85Error",
    "card_hash",
    "decode",
    "encode",
    "encode_stream",
]
