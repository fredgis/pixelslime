"""The on-chain layer — signing, anchoring, and the ``part = 8`` anchor row.

Public surface::

    build_signer(settings)                 -> Signer         # HSM (prod) or local (tests)
    normalize_signature(r, s, hash, addr)  -> Signature      # low-s + v recovery
    Anchorer(web3, addr, signer, ...)      -> .anchor(...)    # idempotent mintCard
    build_anchor_row(serial, ...)          -> Row             # docs/CODEC.md §4.4

Everything raises a subclass of :class:`ChainError` on failure; no private key,
credential or raw secret is ever logged or returned.
"""

from __future__ import annotations

from .anchor import Anchorer, AnchorReceipt
from .anchor_row import (
    AnchorResult,
    build_anchor_row,
    build_anchor_row_from_result,
    encode_anchor_payload,
)
from .config import ChainSettings, load_chain_settings
from .errors import AnchorError, AnchorRowError, ChainError, SignerError
from .signer import (
    KeyVaultSigner,
    LocalSigner,
    Signature,
    SignedTransaction,
    Signer,
    build_signer,
    normalize_signature,
)

__all__ = [
    "AnchorError",
    "AnchorReceipt",
    "AnchorResult",
    "AnchorRowError",
    "Anchorer",
    "ChainError",
    "ChainSettings",
    "KeyVaultSigner",
    "LocalSigner",
    "Signature",
    "SignedTransaction",
    "Signer",
    "SignerError",
    "build_anchor_row",
    "build_anchor_row_from_result",
    "build_signer",
    "encode_anchor_payload",
    "load_chain_settings",
    "normalize_signature",
]
