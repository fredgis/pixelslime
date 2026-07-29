"""The ``part = 8`` anchor row — written after a successful on-chain mint.

``docs/CODEC.md`` §4.4 reserves ``part = 8`` for a 28-byte record that ties an
asmDB card to its NFT: the transaction that minted it, the block it landed in, the
``tokenId``, and a prefix of the ``cardHash`` that was anchored. The row is
addressed exactly like any other PSC-1 row (``id = serial*16 + 8``,
``value = -(serial*16 + 8)``, ``tag = psc.<serial>.8``) so it rides the same asmDB
range/find queries and can never pollute a ``RANGE?lo>=0`` result.

The 28-byte payload is packed **little-endian**, matching the PSC-1 header (§3.1);
§4.4 gives the field offsets but not the byte order, and consistency with the rest
of the stream is the only sane reading. The Z85 envelope is the *existing* codec
implementation (:func:`app.codec.z85.z85_encode`) — there is exactly one Z85 in
this repo and this is not a second one.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.codec.card import Row
from app.codec.z85 import z85_encode

from .errors import AnchorRowError

ANCHOR_PART = 8
ANCHOR_MAGIC = 0x41  # 'A'
ANCHOR_VERSION = 0x01
ANCHOR_PAYLOAD_LEN = 28
ANCHOR_ROW_CHARS = 35  # 28 bytes → 35 Z85 characters

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


def encode_anchor_payload(
    serial: int, tx_hash: bytes, block_number: int, token_id: int, card_hash: bytes
) -> bytes:
    """Pack the 28-byte ``part = 8`` payload exactly as ``docs/CODEC.md`` §4.4 lays out.

    Raises :class:`AnchorRowError` on any out-of-range field rather than silently
    truncating — the same loud-failure discipline the codec keeps (§5.3).
    """
    if not (1 <= serial <= _U16_MAX):
        raise AnchorRowError(f"serial {serial} out of range 1..{_U16_MAX}")
    if not (0 <= block_number <= _U32_MAX):
        raise AnchorRowError(f"block number {block_number} does not fit u32")
    if not (0 <= token_id <= _U32_MAX):
        raise AnchorRowError(f"tokenId {token_id} does not fit u32")
    if len(tx_hash) < 8:
        raise AnchorRowError(f"tx hash is {len(tx_hash)} bytes, need at least 8")
    if len(card_hash) < 8:
        raise AnchorRowError(f"card hash is {len(card_hash)} bytes, need at least 8")

    payload = struct.pack(
        "<BBH8sII8s",
        ANCHOR_MAGIC,
        ANCHOR_VERSION,
        serial,
        tx_hash[:8],
        block_number,
        token_id,
        card_hash[:8],
    )
    if len(payload) != ANCHOR_PAYLOAD_LEN:  # pragma: no cover - guaranteed by the format
        raise AnchorRowError(
            f"anchor payload is {len(payload)} bytes, expected {ANCHOR_PAYLOAD_LEN}"
        )
    return payload


def build_anchor_row(
    serial: int, tx_hash: bytes, block_number: int, token_id: int, card_hash: bytes
) -> Row:
    """Build the addressed asmDB :class:`~app.codec.card.Row` for the anchor.

    ``value`` is negative like every continuation row so it stays out of a header
    range query, and ``tag`` follows the ``psc.<serial>.<part>`` convention (§4.2,
    §4.3). The content is the Z85 of the 28-byte payload — 35 characters.
    """
    payload = encode_anchor_payload(serial, tx_hash, block_number, token_id, card_hash)
    content = z85_encode(payload)
    if len(content) != ANCHOR_ROW_CHARS:  # pragma: no cover - 28 bytes is always 35 chars
        raise AnchorRowError(f"anchor content is {len(content)} chars, expected {ANCHOR_ROW_CHARS}")
    row_id = serial * 16 + ANCHOR_PART
    return Row(id=row_id, value=-row_id, tag=f"psc.{serial}.{ANCHOR_PART}", content=content)


def build_anchor_row_from_result(result: AnchorResult) -> Row:
    """Convenience wrapper: build the row straight from an :class:`AnchorResult`."""
    return build_anchor_row(
        result.serial, result.tx_hash, result.block_number, result.token_id, result.card_hash
    )
