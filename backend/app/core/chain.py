"""Decode the PSC-1 ``part = 8`` on-chain anchor row into the API's ``Chain`` shape.

``app/chain/anchor_row.py`` (W9) *encodes* the anchor row but ships no decoder, so
the read path grows one here. The point of decoding is that ``chain`` (and the
``onChain`` badge that mirrors it) must be driven by the **evidence in asmDB** — the
presence of a well-formed anchor row — and never by the header's ``flags.on_chain``
bit alone: a crash between "set the flag / mint" and "write the anchor row" can leave
a card flagged on-chain with no row, and trusting the flag would then have the gallery
claim a card is anchored while its detail view shows ``chain: null`` (W10's D2).

The 28-byte payload layout and Z85 envelope mirror ``app.chain.anchor_row`` exactly —
same struct, same magic/version, same one Z85 implementation from the codec — so this
decoder and W9's encoder are a matched pair (``docs/CODEC.md`` §4.4).

Only an 8-byte **prefix** of the transaction hash is stored on-chain (§4.4), so
``txHash`` is surfaced as a ``0x``-prefixed 16-hex-character prefix, not a full hash;
``explorerUrl`` is therefore not emitted, since a per-transaction link cannot be built
from a prefix. See the W7 report.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from app.chain.anchor_row import ANCHOR_MAGIC, ANCHOR_PART, ANCHOR_VERSION
from app.codec import Z85Error
from app.codec.z85 import z85_decode

from .logging import get_logger

_log = get_logger(__name__)

#: Little-endian layout of the §4.4 payload: magic, version, serial, tx-hash prefix,
#: block number, tokenId, card-hash prefix — byte-identical to the W9 encoder.
_ANCHOR_STRUCT = struct.Struct("<BBH8sII8s")

#: asmDB row id / part for the anchor row, re-exported for the source adapter.
ANCHOR_ROW_PART = ANCHOR_PART


@dataclass(frozen=True)
class ChainAnchor:
    """The on-chain facts decoded from a ``part = 8`` anchor row.

    ``tx_hash_prefix`` and ``card_hash_prefix`` are the 8-byte prefixes §4.4 stores;
    the full hashes are not recoverable from asmDB.
    """

    serial: int
    token_id: int
    block_number: int
    tx_hash_prefix: bytes
    card_hash_prefix: bytes

    @property
    def tx_hash(self) -> str:
        """The stored transaction-hash prefix as ``0x`` + 16 hex characters."""
        return "0x" + self.tx_hash_prefix.hex()

    def to_api_dict(self) -> dict[str, Any]:
        """Project onto the contract's ``Chain`` object (``tokenId``/``txHash``/``blockNumber``)."""
        return {
            "tokenId": self.token_id,
            "txHash": self.tx_hash,
            "blockNumber": self.block_number,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialise losslessly for the ``index.json`` warm-start snapshot."""
        return {
            "serial": self.serial,
            "tokenId": self.token_id,
            "blockNumber": self.block_number,
            "txHashPrefix": self.tx_hash_prefix.hex(),
            "cardHashPrefix": self.card_hash_prefix.hex(),
        }

    @classmethod
    def from_storage_dict(cls, data: object) -> ChainAnchor | None:
        """Rebuild from :meth:`to_storage_dict`; return ``None`` on any malformed input."""
        if not isinstance(data, dict):
            return None
        try:
            return cls(
                serial=int(data["serial"]),
                token_id=int(data["tokenId"]),
                block_number=int(data["blockNumber"]),
                tx_hash_prefix=bytes.fromhex(str(data["txHashPrefix"])),
                card_hash_prefix=bytes.fromhex(str(data["cardHashPrefix"])),
            )
        except (KeyError, TypeError, ValueError):
            return None


def decode_anchor_content(content: str, *, serial: int) -> ChainAnchor | None:
    """Decode a ``part = 8`` row's content, or return ``None`` if it is not a valid anchor.

    Returns ``None`` (never raises) on any structural problem — bad Z85, wrong length,
    wrong magic/version, or a serial that does not match the row it was read for — so a
    single corrupt anchor row degrades that one card to "not anchored" instead of
    failing index construction. Every rejection is logged so the state is never silent.
    """
    try:
        raw = z85_decode(content)
    except Z85Error:
        _log.warning("anchor_decode_failed", serial=serial, reason="z85")
        return None
    if len(raw) < _ANCHOR_STRUCT.size:
        _log.warning("anchor_decode_failed", serial=serial, reason="short")
        return None

    magic, version, row_serial, tx_prefix, block_number, token_id, card_prefix = (
        _ANCHOR_STRUCT.unpack(raw[: _ANCHOR_STRUCT.size])
    )
    if magic != ANCHOR_MAGIC or version != ANCHOR_VERSION:
        _log.warning("anchor_decode_failed", serial=serial, reason="magic")
        return None
    if row_serial != serial:
        _log.warning("anchor_serial_mismatch", serial=serial, row_serial=row_serial)
        return None

    return ChainAnchor(
        serial=serial,
        token_id=token_id,
        block_number=block_number,
        tx_hash_prefix=tx_prefix,
        card_hash_prefix=card_prefix,
    )
