"""The fixed 32-byte PSC-1 header: little-endian binary layout and its bitfields.

This module owns the byte-exact layout from ``docs/CODEC.md`` §3.1 and the two
packed words that need bit surgery: ``flags_rarity_type`` at offset 7 (rarity in
bits 0-2, type in bits 3-6, shiny in bit 7) and the ``flags`` word at offset 22.
It knows nothing about compression or Z85 — it just turns a struct of integers
into 32 deterministic little-endian bytes and back, failing loudly on a bad
magic, version, reserved bit or out-of-range enum. The ``crc16`` field is packed
last and computed by the caller over ``prefix`` + body, so this module exposes the
30-byte ``prefix`` separately.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import HeaderError

MAGIC = 0x50  # 'P'
VERSION = 1
HEADER_LEN = 32

# Offsets 0..29 (everything except the trailing u16 crc16).
_PREFIX_FMT = "<BBHHBBHHBBBBBBBBBBHH4s"
# Full 32-byte header including crc16.
_FULL_FMT = _PREFIX_FMT + "H"

_PREFIX_LEN = struct.calcsize(_PREFIX_FMT)
assert struct.calcsize(_FULL_FMT) == HEADER_LEN, "header layout must be exactly 32 bytes"
assert _PREFIX_LEN == HEADER_LEN - 2, "prefix must be header minus the 2-byte crc"

_MAX_RARITY = 5  # rarity uses 3 bits but only 0..5 are defined


@dataclass(frozen=True, slots=True)
class Header:
    """The decoded contents of a 32-byte PSC-1 header."""

    serial: int
    total_len: int
    level: int
    rarity: int
    type_id: int
    shiny: bool
    height_mm: int
    weight_g: int
    strength: int
    endurance: int
    agility: int
    happiness: int
    art_id: int
    style_id: int
    frame_id: int
    background_id: int
    biome_id: int
    mood_id: int
    has_companion: bool
    has_accessory: bool
    verified: bool
    on_chain: bool
    seed: bool
    mint_day: int
    art_sha: bytes
    crc16: int = 0

    def _flags_rarity_type(self) -> int:
        return (self.rarity & 0x07) | ((self.type_id & 0x0F) << 3) | ((self.shiny & 1) << 7)

    def _flags_word(self) -> int:
        return (
            (self.has_companion & 1)
            | ((self.has_accessory & 1) << 1)
            | ((self.verified & 1) << 2)
            | ((self.on_chain & 1) << 3)
            | ((self.seed & 1) << 4)
        )

    def prefix(self) -> bytes:
        """Return header bytes ``0..29`` (all fields except the trailing crc16).

        This is the slice the CRC is computed over (concatenated with the body),
        and the caller appends ``crc16`` to it to finish the 32-byte header.
        """
        if len(self.art_sha) != 4:
            raise HeaderError(f"art_sha must be 4 bytes, got {len(self.art_sha)}")
        try:
            return struct.pack(
                _PREFIX_FMT,
                MAGIC,
                VERSION,
                self.serial,
                self.total_len,
                self.level,
                self._flags_rarity_type(),
                self.height_mm,
                self.weight_g,
                self.strength,
                self.endurance,
                self.agility,
                self.happiness,
                self.art_id,
                self.style_id,
                self.frame_id,
                self.background_id,
                self.biome_id,
                self.mood_id,
                self._flags_word(),
                self.mint_day,
                self.art_sha,
            )
        except struct.error as exc:
            raise HeaderError(f"header field out of range: {exc}") from exc

    def pack(self) -> bytes:
        """Return the full 32-byte header using ``self.crc16`` verbatim."""
        return self.prefix() + struct.pack("<H", self.crc16 & 0xFFFF)

    @classmethod
    def unpack(cls, data: bytes) -> Header:
        """Parse 32 header bytes, validating magic, version and reserved bits."""
        if len(data) < HEADER_LEN:
            raise HeaderError(f"header needs {HEADER_LEN} bytes, got {len(data)}")
        fields = struct.unpack(_FULL_FMT, data[:HEADER_LEN])
        # fmt: off
        (
            magic, version, serial, total_len, level, frt, height_mm, weight_g,
            strength, endurance, agility, happiness, art_id, style_id, frame_id,
            background_id, biome_id, mood_id, flags_word, mint_day, art_sha, crc16,
        ) = fields
        # fmt: on

        if magic != MAGIC:
            raise HeaderError(f"bad magic 0x{magic:02x}, expected 0x{MAGIC:02x}")
        if version != VERSION:
            raise HeaderError(f"unsupported version {version}, expected {VERSION}")

        rarity = frt & 0x07
        type_id = (frt >> 3) & 0x0F
        shiny = bool((frt >> 7) & 0x01)
        if rarity > _MAX_RARITY:
            raise HeaderError(f"undefined rarity ordinal {rarity}")

        if flags_word >> 5:
            raise HeaderError(f"reserved flag bits must be 0, got 0x{flags_word:04x}")

        return cls(
            serial=serial,
            total_len=total_len,
            level=level,
            rarity=rarity,
            type_id=type_id,
            shiny=shiny,
            height_mm=height_mm,
            weight_g=weight_g,
            strength=strength,
            endurance=endurance,
            agility=agility,
            happiness=happiness,
            art_id=art_id,
            style_id=style_id,
            frame_id=frame_id,
            background_id=background_id,
            biome_id=biome_id,
            mood_id=mood_id,
            has_companion=bool(flags_word & 0x01),
            has_accessory=bool((flags_word >> 1) & 0x01),
            verified=bool((flags_word >> 2) & 0x01),
            on_chain=bool((flags_word >> 3) & 0x01),
            seed=bool((flags_word >> 4) & 0x01),
            mint_day=mint_day,
            art_sha=art_sha,
            crc16=crc16,
        )
