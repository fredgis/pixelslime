"""The ``part = 8`` anchor row — written after a successful on-chain mint.

``docs/CODEC.md`` §4.4 defines ``part = 8`` as the record that ties an asmDB card to
its NFT: the transaction that minted it, the block it landed in, the ``tokenId``, and
the ``cardHash`` that was anchored. The row is addressed exactly like any other PSC-1
row (``id = serial*16 + 8``, ``value = -(serial*16 + 8)``, ``tag = psc.<serial>.8``)
so it rides the same asmDB range/find queries and can never pollute a ``RANGE?lo>=0``
result.

**Version 0x02 (current)** stores the *full* 32-byte transaction and card hashes — 76
bytes → 95 Z85 characters, of the 175 available. **Version 0x01** stored only the
first 8 bytes of each hash (28 bytes); W7 found that an 8-byte prefix cannot build a
working block-explorer link — the whole point of the row — so 0x02 supersedes it. No
card was ever anchored under 0x01, so in practice only 0x02 is written; the decoder
still accepts 0x01 (yielding prefixes and *no* ``explorer_url``) so the version byte
means something.

Both an **encoder** (:func:`build_anchor_row`) and a **decoder**
(:func:`decode_anchor_row`) live here — this module is the one canonical home for the
part-8 wire format. Payloads are packed **little-endian**, matching the PSC-1 header
(§3.1); §4.4 gives offsets but not byte order, and consistency with the rest of the
stream is the only sane reading. The Z85 envelope is the *existing* codec
implementation (:func:`app.codec.z85`) — there is exactly one Z85 in this repo and
this is not a second one.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.codec import Z85Error
from app.codec.card import Row
from app.codec.z85 import z85_decode, z85_encode

from .errors import AnchorRowError

ANCHOR_PART = 8
ANCHOR_MAGIC = 0x41  # 'A'

# The current write version stores the FULL 32-byte hashes so a real per-transaction
# explorer link can be built; 0x01 stored only 8-byte prefixes and is decode-only now.
ANCHOR_VERSION = 0x02
ANCHOR_VERSION_LEGACY = 0x01

# Little-endian, matching the PSC-1 header (§3.1): magic, version, serial u16,
# tx hash, block u32, tokenId u32, card hash.
_STRUCT_V2 = struct.Struct("<BBH32sII32s")  # 76 bytes — full hashes
_STRUCT_V1 = struct.Struct("<BBH8sII8s")  # 28 bytes — legacy 8-byte prefixes
_STRUCT_BY_VERSION: dict[int, struct.Struct] = {
    ANCHOR_VERSION: _STRUCT_V2,
    ANCHOR_VERSION_LEGACY: _STRUCT_V1,
}
_HASH_LEN_BY_VERSION: dict[int, int] = {ANCHOR_VERSION: 32, ANCHOR_VERSION_LEGACY: 8}

ANCHOR_PAYLOAD_LEN = _STRUCT_V2.size  # 76 — the current (0x02) payload
ANCHOR_ROW_CHARS = ANCHOR_PAYLOAD_LEN // 4 * 5  # 95 Z85 characters

_FULL_HASH_LEN = 32

# Polygon Amoy is the settled chain (docs/PLAN.md §8.7); a 0x02 row carries the full
# transaction hash, which is exactly what a per-transaction explorer link needs.
AMOY_EXPLORER_TX_BASE = "https://amoy.polygonscan.com/tx/"

_U16_MAX = 0xFFFF
_U32_MAX = 0xFFFFFFFF


@dataclass(frozen=True)
class AnchorResult:
    """The on-chain facts an anchor row is built from (see :mod:`app.chain.anchor`)."""

    serial: int
    tx_hash: bytes
    block_number: int
    token_id: int
    card_hash: bytes


@dataclass(frozen=True)
class ChainAnchor:
    """The on-chain facts decoded back out of a ``part = 8`` anchor row.

    ``version`` records which layout the row used: ``0x02`` carries the full 32-byte
    transaction and card hashes (and therefore a working :attr:`explorer_url`); the
    historical ``0x01`` carries only 8-byte prefixes and yields no link. This is the
    inverse of :class:`AnchorResult` — encode a result, decode a :class:`ChainAnchor`.
    """

    version: int
    serial: int
    token_id: int
    block_number: int
    tx_hash: bytes
    card_hash: bytes

    @property
    def full_hashes(self) -> bool:
        """True when the full 32-byte hashes are present (a version ``0x02`` row)."""
        return len(self.tx_hash) == _FULL_HASH_LEN

    @property
    def tx_hash_hex(self) -> str:
        """The stored transaction hash as ``0x`` + hex (64 chars for 0x02, 16 for 0x01)."""
        return "0x" + self.tx_hash.hex()

    @property
    def card_hash_hex(self) -> str:
        """The stored card hash as ``0x`` + hex."""
        return "0x" + self.card_hash.hex()

    @property
    def explorer_url(self) -> str | None:
        """A working Amoy explorer link — only when the full tx hash is stored (0x02)."""
        if not self.full_hashes:
            return None
        return AMOY_EXPLORER_TX_BASE + self.tx_hash_hex


def encode_anchor_payload(
    serial: int,
    tx_hash: bytes,
    block_number: int,
    token_id: int,
    card_hash: bytes,
    *,
    version: int = ANCHOR_VERSION,
) -> bytes:
    """Pack the ``part = 8`` payload exactly as ``docs/CODEC.md`` §4.4 lays out.

    ``version`` selects the layout: the current ``0x02`` stores the **full 32-byte**
    transaction and card hashes (76 bytes); the historical ``0x01`` stored only
    8-byte prefixes (28 bytes) and is kept solely so the decoder can round-trip old
    rows — nothing writes it now. Raises :class:`AnchorRowError` on an unknown version
    or any out-of-range field rather than silently truncating (§5.3).
    """
    fmt = _STRUCT_BY_VERSION.get(version)
    if fmt is None:
        raise AnchorRowError(f"cannot encode unknown anchor version 0x{version:02x}")
    if not (1 <= serial <= _U16_MAX):
        raise AnchorRowError(f"serial {serial} out of range 1..{_U16_MAX}")
    if not (0 <= block_number <= _U32_MAX):
        raise AnchorRowError(f"block number {block_number} does not fit u32")
    if not (0 <= token_id <= _U32_MAX):
        raise AnchorRowError(f"tokenId {token_id} does not fit u32")
    hash_len = _HASH_LEN_BY_VERSION[version]
    if len(tx_hash) < hash_len:
        raise AnchorRowError(f"tx hash is {len(tx_hash)} bytes, need at least {hash_len}")
    if len(card_hash) < hash_len:
        raise AnchorRowError(f"card hash is {len(card_hash)} bytes, need at least {hash_len}")

    payload = fmt.pack(
        ANCHOR_MAGIC,
        version,
        serial,
        tx_hash[:hash_len],
        block_number,
        token_id,
        card_hash[:hash_len],
    )
    if len(payload) != fmt.size:  # pragma: no cover - guaranteed by the format
        raise AnchorRowError(f"anchor payload is {len(payload)} bytes, expected {fmt.size}")
    return payload


def build_anchor_row(
    serial: int,
    tx_hash: bytes,
    block_number: int,
    token_id: int,
    card_hash: bytes,
    *,
    version: int = ANCHOR_VERSION,
) -> Row:
    """Build the addressed asmDB :class:`~app.codec.card.Row` for the anchor.

    ``value`` is negative like every continuation row so it stays out of a header
    range query, and ``tag`` follows the ``psc.<serial>.<part>`` convention (§4.2,
    §4.3). The content is the Z85 of the payload — 95 characters for a ``0x02`` row.
    """
    payload = encode_anchor_payload(
        serial, tx_hash, block_number, token_id, card_hash, version=version
    )
    content = z85_encode(payload)
    expected_chars = len(payload) // 4 * 5
    if len(content) != expected_chars:  # pragma: no cover - z85 is 4 bytes → 5 chars
        raise AnchorRowError(f"anchor content is {len(content)} chars, expected {expected_chars}")
    row_id = serial * 16 + ANCHOR_PART
    return Row(id=row_id, value=-row_id, tag=f"psc.{serial}.{ANCHOR_PART}", content=content)


def build_anchor_row_from_result(result: AnchorResult, *, version: int = ANCHOR_VERSION) -> Row:
    """Convenience wrapper: build the row straight from an :class:`AnchorResult`."""
    return build_anchor_row(
        result.serial,
        result.tx_hash,
        result.block_number,
        result.token_id,
        result.card_hash,
        version=version,
    )


def decode_anchor_payload(payload: bytes) -> ChainAnchor:
    """Decode a raw ``part = 8`` payload into a :class:`ChainAnchor`.

    Dispatches on the version byte and validates hard: a bad magic, an unknown
    version, or a length that does not match the version's fixed layout each raise
    :class:`AnchorRowError`. This is the loud-failure inverse of
    :func:`encode_anchor_payload` (§5.3).
    """
    if len(payload) < 2:
        raise AnchorRowError(f"anchor payload is {len(payload)} bytes, too short to read a header")
    magic, version = payload[0], payload[1]
    if magic != ANCHOR_MAGIC:
        raise AnchorRowError(f"bad anchor magic 0x{magic:02x}, expected 0x{ANCHOR_MAGIC:02x}")
    fmt = _STRUCT_BY_VERSION.get(version)
    if fmt is None:
        raise AnchorRowError(f"unknown anchor version 0x{version:02x}")
    if len(payload) != fmt.size:
        raise AnchorRowError(
            f"anchor payload is {len(payload)} bytes, expected {fmt.size} "
            f"for version 0x{version:02x}"
        )
    _magic, _version, serial, tx_hash, block_number, token_id, card_hash = fmt.unpack(payload)
    return ChainAnchor(
        version=version,
        serial=serial,
        token_id=token_id,
        block_number=block_number,
        tx_hash=tx_hash,
        card_hash=card_hash,
    )


def decode_anchor_row(content: str, *, expected_serial: int | None = None) -> ChainAnchor:
    """Decode a ``part = 8`` row's Z85 content into a :class:`ChainAnchor`.

    The canonical read path for the part-8 wire format: the inverse of
    :func:`build_anchor_row`, accepting **both** layouts (``0x02`` full hashes,
    ``0x01`` prefixes). Raises :class:`AnchorRowError` on invalid Z85, a bad magic, an
    unknown version, a length mismatch, or — when ``expected_serial`` is given — a
    serial that does not match the row it was read for.
    """
    try:
        payload = z85_decode(content)
    except Z85Error as exc:
        raise AnchorRowError(f"anchor content is not valid Z85: {exc}") from exc
    anchor = decode_anchor_payload(payload)
    if expected_serial is not None and anchor.serial != expected_serial:
        raise AnchorRowError(
            f"anchor serial {anchor.serial} does not match expected {expected_serial}"
        )
    return anchor


def try_decode_anchor_row(
    content: str, *, expected_serial: int | None = None
) -> ChainAnchor | None:
    """Non-raising :func:`decode_anchor_row`: return ``None`` on any anchor-row fault.

    For read paths that must degrade a single corrupt row to "not anchored" rather
    than fail wholesale (e.g. index construction), instead of wrapping the raising
    form at every call site.
    """
    try:
        return decode_anchor_row(content, expected_serial=expected_serial)
    except AnchorRowError:
        return None
