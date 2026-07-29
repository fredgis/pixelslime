"""Core's view of the on-chain anchor: project and persist W9's :class:`ChainAnchor`.

The canonical ``part = 8`` wire format — encoder *and* decoder — lives in
:mod:`app.chain.anchor_row` (W9). This module owns only what the *read path* layers on
top of it:

* :func:`read_anchor` — decode a *present* anchor row, degrading a corrupt one to
  ``None`` with a loud log instead of raising, so one bad row skips a single card
  rather than taking startup down (the resilience the index already gives a missing
  continuation row).
* :func:`chain_api_dict` — project a decoded anchor onto the contract's ``chain``
  object (``tokenId`` / ``txHash`` / ``blockNumber`` / ``explorerUrl``).
* :func:`chain_storage_dict` / :func:`chain_from_storage_dict` — round-trip an anchor
  through the ``index.json`` warm-start snapshot losslessly.

``chain`` (and the ``onChain`` badge that mirrors it) is driven by the *evidence* — a
well-formed anchor row — never by the header's ``flags.on_chain`` bit, which a crash
between mint and anchor-write can leave set with no row (W10's D2). ``ChainAnchor`` is
re-exported here so the rest of ``core`` has one import site, but it stays W9's single
type — this module defines no second copy of it.

The current ``0x02`` row carries the full 32-byte transaction hash, so ``explorerUrl``
is a real per-transaction link; the historical ``0x01`` row stored only an 8-byte
prefix and yields no link, so :func:`chain_api_dict` omits ``explorerUrl`` in that case
(the contract's ``explorerUrl`` is a non-nullable ``string``).
"""

from __future__ import annotations

from typing import Any

from app.chain import ChainAnchor, try_decode_anchor_row
from app.chain.anchor_row import ANCHOR_PART

from .logging import get_logger

_log = get_logger(__name__)

#: asmDB row part for the anchor row, re-exported for the source adapter's id maths.
ANCHOR_ROW_PART = ANCHOR_PART

__all__ = [
    "ANCHOR_ROW_PART",
    "ChainAnchor",
    "chain_api_dict",
    "chain_from_storage_dict",
    "chain_storage_dict",
    "read_anchor",
]


def read_anchor(content: str, *, serial: int) -> ChainAnchor | None:
    """Decode a *present* ``part = 8`` row's content, or ``None`` if it will not decode.

    Delegates the bytes to W9's non-raising :func:`app.chain.try_decode_anchor_row`,
    pinning ``expected_serial`` so a row addressed to another serial is rejected.
    Callers reach here only once they already hold a row, so a ``None`` means the row
    is present but corrupt — logged loudly so a partially-written or malformed anchor is
    never a silent "not anchored".
    """
    anchor = try_decode_anchor_row(content, expected_serial=serial)
    if anchor is None:
        _log.warning("anchor_row_corrupt", serial=serial)
    return anchor


def chain_api_dict(anchor: ChainAnchor) -> dict[str, Any]:
    """Project a decoded anchor onto the contract's ``chain`` object.

    ``txHash`` is the stored transaction hash as ``0x`` + hex. ``explorerUrl`` is
    included only when the full 32-byte hash is present (a ``0x02`` row): a working
    per-transaction link cannot be built from the legacy 8-byte prefix, and the
    contract types ``explorerUrl`` as a non-nullable ``string``, so it is omitted
    rather than emitted as ``null`` for a ``0x01`` row.
    """
    data: dict[str, Any] = {
        "tokenId": anchor.token_id,
        "txHash": anchor.tx_hash_hex,
        "blockNumber": anchor.block_number,
    }
    explorer = anchor.explorer_url
    if explorer is not None:
        data["explorerUrl"] = explorer
    return data


def chain_storage_dict(anchor: ChainAnchor) -> dict[str, Any]:
    """Serialise a decoded anchor losslessly for the ``index.json`` warm-start snapshot.

    Stores the full hashes as hex and keeps the ``version`` byte, so a warm restart
    reconstructs the exact anchor (and therefore the same ``explorerUrl``) without
    re-reading asmDB.
    """
    return {
        "version": anchor.version,
        "serial": anchor.serial,
        "tokenId": anchor.token_id,
        "blockNumber": anchor.block_number,
        "txHash": anchor.tx_hash.hex(),
        "cardHash": anchor.card_hash.hex(),
    }


def chain_from_storage_dict(data: object) -> ChainAnchor | None:
    """Rebuild a :class:`ChainAnchor` from :func:`chain_storage_dict`; ``None`` if malformed."""
    if not isinstance(data, dict):
        return None
    try:
        return ChainAnchor(
            version=int(data["version"]),
            serial=int(data["serial"]),
            token_id=int(data["tokenId"]),
            block_number=int(data["blockNumber"]),
            tx_hash=bytes.fromhex(str(data["txHash"])),
            card_hash=bytes.fromhex(str(data["cardHash"])),
        )
    except (KeyError, TypeError, ValueError):
        return None
