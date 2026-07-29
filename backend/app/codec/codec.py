"""The PSC-1 codec proper: ``encode`` / ``decode`` / ``encode_stream`` / ``card_hash``.

This module orchestrates the pieces — header packing, DEFLATE with the pinned
dictionary, CRC, Z85 and the row-addressing arithmetic — into the four public
functions from ``docs/CODEC.md`` §6. The design invariants it is responsible for:

* the emitted ``content`` of every row is text asmDB will accept (§5.5), checked
  before returning rather than only in tests;
* nothing is ever silently truncated or defaulted — an over-long field, an
  oversized stream, a bad CRC or a missing row all raise (§5.3);
* the ``value`` sign convention (positive mint-date on part 0, negative on every
  continuation row) is what keeps continuation rows out of a ``RANGE`` query, so
  it is produced on encode and re-checked on decode (§4.2).
"""

from __future__ import annotations

import datetime as _dt
import struct
import zlib

from .card import RARITIES, TYPES, Card, Flags, Row
from .crc import crc16_ccitt_false
from .dictionary import load_dictionary
from .errors import (
    BodyError,
    CodecError,
    CrcError,
    FieldLimitError,
    RowError,
    StreamTooLargeError,
)
from .header import HEADER_LEN, Header
from .keccak import keccak256
from .z85 import z85_decode, z85_encode

try:  # pydantic is a declared dependency; import kept narrow for the wrap below
    from pydantic import ValidationError
except ImportError:  # pragma: no cover - pydantic is always present
    ValidationError = Exception  # type: ignore[assignment,misc]

SEP = b"\x1f"
CHUNK = 140  # binary bytes per asmDB row (floor(175/5)*4)
MAX_CHUNKS = 4
MAX_STREAM = CHUNK * MAX_CHUNKS  # 560
CONTENT_MAX_BYTES = 175
TAG_MAX_BYTES = 39
EPOCH = _dt.date(2026, 1, 1)

# (attribute, char limit, UTF-8 byte limit) in on-wire order — §3.5 / §3.6.
_TEXT_FIELDS: tuple[tuple[str, int, int], ...] = (
    ("name", 18, 36),
    ("personality", 90, 180),
    ("power_name", 20, 40),
    ("power_desc", 90, 180),
    ("quote", 40, 80),
)
_FORBIDDEN = ("\x00", "\x1f", "\r", "\n")


def _mint_value(mint_day: int) -> int:
    """Return the header row's ``value``: the mint date as a positive ``YYYYMMDD``.

    Positive by construction so ``RANGE?lo>=0`` returns headers only; continuation
    rows carry a negative value and are excluded (§4.2).
    """
    day = EPOCH + _dt.timedelta(days=mint_day)
    return day.year * 10000 + day.month * 100 + day.day


def _joined_body_fields(card: Card) -> bytes:
    """Validate the five text fields (char + byte limits, forbidden bytes) and join.

    The char limits duplicate the schema, but the UTF-8 byte limits from §3.6 are a
    stricter, independent guard (one character can be four bytes), so this must run
    even for a schema-valid card. Raises :class:`FieldLimitError`, never truncates.
    """
    parts: list[bytes] = []
    for attr, char_max, byte_max in _TEXT_FIELDS:
        value: str = getattr(card, attr)
        if not value:
            raise FieldLimitError(f"{attr} must not be empty")
        if len(value) > char_max:
            raise FieldLimitError(f"{attr} is {len(value)} chars, limit is {char_max}")
        for bad in _FORBIDDEN:
            if bad in value:
                raise FieldLimitError(f"{attr} contains forbidden control byte {bad!r}")
        encoded = value.encode("utf-8")
        if len(encoded) > byte_max:
            raise FieldLimitError(f"{attr} is {len(encoded)} UTF-8 bytes, limit is {byte_max}")
        parts.append(encoded)
    return SEP.join(parts)


def _deflate(payload: bytes) -> bytes:
    """Raw DEFLATE (``wbits=-15``) with the pinned preset dictionary (§3.5)."""
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15, zdict=load_dictionary())
    return compressor.compress(payload) + compressor.flush()


def _inflate(blob: bytes) -> bytes:
    """Inverse of :func:`_deflate`; raises :class:`BodyError` on malformed input."""
    decompressor = zlib.decompressobj(wbits=-15, zdict=load_dictionary())
    try:
        return decompressor.decompress(blob) + decompressor.flush()
    except zlib.error as exc:
        raise BodyError(f"cannot inflate body: {exc}") from exc


def _header_for(card: Card, total_len: int) -> Header:
    """Project a validated :class:`Card` onto the integer header struct."""
    return Header(
        serial=card.serial,
        total_len=total_len,
        level=card.level,
        rarity=RARITIES.index(card.rarity),
        type_id=TYPES.index(card.type),
        shiny=card.shiny,
        height_mm=card.height_mm,
        weight_g=card.weight_g,
        strength=card.strength,
        endurance=card.endurance,
        agility=card.agility,
        happiness=card.happiness,
        art_id=card.art_id,
        style_id=card.style_id,
        frame_id=card.frame_id,
        background_id=card.background_id,
        biome_id=card.biome_id,
        mood_id=card.mood_id,
        has_companion=card.flags.has_companion,
        has_accessory=card.flags.has_accessory,
        verified=card.flags.verified,
        on_chain=card.flags.on_chain,
        seed=card.flags.seed,
        companion_id=card.companion_id,
        mint_day=card.mint_day,
        art_sha=bytes.fromhex(card.art_sha),
    )


def encode_stream(card: Card) -> bytes:
    """Serialise a card to the raw PSC-1 byte stream (header + compressed body).

    This is the canonical binary form; ``card_hash`` and the on-chain anchor are
    both derived from it, never from the JSON, because JSON key order is not
    canonical.
    """
    body = _deflate(_joined_body_fields(card))
    total_len = HEADER_LEN + len(body)
    prefix = _header_for(card, total_len).prefix()
    crc = crc16_ccitt_false(prefix + body)
    stream = prefix + struct.pack("<H", crc) + body
    if len(stream) != total_len:  # pragma: no cover - guarded by construction
        raise CodecError(f"stream length {len(stream)} != declared {total_len}")
    return stream


def _guard_content(content: str) -> None:
    """Fail loudly if a row's ``content`` is anything asmDB would reject (§5.5)."""
    encoded = content.encode("utf-8")
    if len(encoded) > CONTENT_MAX_BYTES:
        raise CodecError(f"content is {len(encoded)} bytes, asmDB limit is {CONTENT_MAX_BYTES}")
    if b"\x00" in encoded or b"\r" in encoded or b"\n" in encoded:
        raise CodecError("content contains a NUL, CR or LF byte")


def _split_rows(stream: bytes, serial: int, mint_day: int) -> list[Row]:
    """Chunk a stream into addressed rows, enforcing the 4-row / 560-byte ceiling."""
    if len(stream) > MAX_STREAM:
        raise StreamTooLargeError(
            f"stream is {len(stream)} bytes, ceiling is {MAX_STREAM} ({MAX_CHUNKS} rows)"
        )
    num_chunks = -(-len(stream) // CHUNK) or 1  # ceil, at least one row
    mint_value = _mint_value(mint_day)
    rows: list[Row] = []
    for part in range(num_chunks):
        chunk = stream[part * CHUNK : part * CHUNK + CHUNK]
        content = z85_encode(chunk)
        _guard_content(content)
        row_id = serial * 16 + part
        value = mint_value if part == 0 else -row_id
        tag = f"psc.{serial}.{part}"
        if len(tag.encode("utf-8")) > TAG_MAX_BYTES or " " in tag:
            raise RowError(f"tag {tag!r} is invalid")
        rows.append(Row(id=row_id, value=value, tag=tag, content=content))
    return rows


def encode(card: Card) -> list[Row]:
    """Encode a card into ordered asmDB rows (part 0 first). Raises on any violation."""
    return _split_rows(encode_stream(card), serial=card.serial, mint_day=card.mint_day)


def card_hash(card: Card) -> bytes:
    """Return ``keccak256`` (the Ethereum variant) of the canonical stream — 32 bytes."""
    return keccak256(encode_stream(card))


def _reassemble(rows: list[Row]) -> tuple[bytes, Header, Row, int]:
    """Rebuild the stream from rows, order-insensitively, with full consistency checks."""
    if not rows:
        raise RowError("no rows to decode")

    by_id: dict[int, Row] = {}
    for row in rows:
        existing = by_id.get(row.id)
        if existing is not None and existing.content != row.content:
            raise RowError(f"conflicting rows for id {row.id}")
        by_id[row.id] = row

    headers = [row for row in by_id.values() if row.id % 16 == 0]
    if not headers:
        raise RowError("missing header row (part 0)")
    if len(headers) > 1:
        raise RowError("multiple header rows: rows span more than one card")
    row0 = headers[0]
    serial = row0.id // 16

    header = Header.unpack(z85_decode(row0.content)[:HEADER_LEN])
    if header.serial != serial:
        raise RowError(f"header serial {header.serial} != row id serial {serial}")

    total_len = header.total_len
    if total_len < HEADER_LEN:
        raise RowError(f"total_len {total_len} is smaller than the header")
    if total_len > MAX_STREAM:
        raise StreamTooLargeError(f"total_len {total_len} exceeds ceiling {MAX_STREAM}")
    num_chunks = -(-total_len // CHUNK)

    decoded = bytearray()
    for part in range(num_chunks):
        part_row = by_id.get(serial * 16 + part)
        if part_row is None:
            raise RowError(f"missing continuation row: part {part} of serial {serial}")
        expected_value = _mint_value(header.mint_day) if part == 0 else -(serial * 16 + part)
        if part_row.value != expected_value:
            raise RowError(f"row part {part} value {part_row.value} != expected {expected_value}")
        if part_row.tag != f"psc.{serial}.{part}":
            raise RowError(f"row part {part} tag {part_row.tag!r} is inconsistent")
        decoded += z85_decode(part_row.content)

    if len(decoded) < total_len:
        raise RowError(f"reassembled {len(decoded)} bytes, need {total_len}")
    if any(decoded[total_len:]):
        raise RowError("non-zero Z85 padding after end of stream")
    return bytes(decoded[:total_len]), header, row0, num_chunks


def decode(rows: list[Row]) -> Card:
    """Decode asmDB rows back into a card. Order-insensitive; raises on any violation."""
    stream, header, _row0, _num_chunks = _reassemble(rows)

    body = stream[HEADER_LEN:]
    if crc16_ccitt_false(stream[: HEADER_LEN - 2] + body) != header.crc16:
        raise CrcError("CRC-16 mismatch: the stream is corrupt or a row is wrong")

    fields = _inflate(body).split(SEP)
    if len(fields) != len(_TEXT_FIELDS):
        raise BodyError(f"body holds {len(fields)} fields, expected {len(_TEXT_FIELDS)}")
    try:
        name, personality, power_name, power_desc, quote = (f.decode("utf-8") for f in fields)
    except UnicodeDecodeError as exc:
        raise BodyError(f"body field is not valid UTF-8: {exc}") from exc

    payload = {
        "series": "PS",
        "serial": header.serial,
        "name": name,
        "level": header.level,
        "rarity": RARITIES[header.rarity],
        "type": TYPES[header.type_id],
        "height_mm": header.height_mm,
        "weight_g": header.weight_g,
        "strength": header.strength,
        "endurance": header.endurance,
        "agility": header.agility,
        "happiness": header.happiness,
        "art_id": header.art_id,
        "style_id": header.style_id,
        "frame_id": header.frame_id,
        "background_id": header.background_id,
        "biome_id": header.biome_id,
        "mood_id": header.mood_id,
        "personality": personality,
        "power_name": power_name,
        "power_desc": power_desc,
        "quote": quote,
        "mint_day": header.mint_day,
        "shiny": header.shiny,
        "flags": Flags(
            has_companion=header.has_companion,
            has_accessory=header.has_accessory,
            verified=header.verified,
            on_chain=header.on_chain,
            seed=header.seed,
        ),
        "companion_id": header.companion_id,
        "art_sha": header.art_sha.hex(),
    }
    try:
        return Card.model_validate(payload)
    except ValidationError as exc:
        raise BodyError(f"decoded card failed validation: {exc}") from exc
