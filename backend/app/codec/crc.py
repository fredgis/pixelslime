"""CRC-16/CCITT-FALSE — the integrity check over the whole PSC-1 stream.

This is the specific CRC-16 variant with polynomial ``0x1021``, initial value
``0xFFFF``, **no** input/output reflection and **no** final XOR (catalogue name
``CRC-16/CCITT-FALSE``). It is computed over header bytes ``0..29`` concatenated
with the compressed body — the ``crc16`` field itself is excluded — and verified
on decode so that a missing or corrupted row is caught rather than silently
decoded into a plausible-looking wrong card. See ``docs/CODEC.md`` §3.1 / §4.

Bit-by-bit rather than table-driven: the payload is only a few hundred bytes, so
clarity beats the micro-optimisation of a precomputed table.
"""

from __future__ import annotations

_POLY = 0x1021
_INIT = 0xFFFF
_MASK = 0xFFFF


def crc16_ccitt_false(data: bytes) -> int:
    """Return the CRC-16/CCITT-FALSE of ``data`` as a 16-bit integer."""
    crc = _INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ _POLY) & _MASK if crc & 0x8000 else (crc << 1) & _MASK
    return crc
