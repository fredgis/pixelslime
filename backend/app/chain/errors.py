"""Exception hierarchy for the on-chain layer.

Mirroring :mod:`app.codec.errors`, every failure mode in this package raises a
subclass of :class:`ChainError` so a caller can catch the whole chain layer with a
single ``except ChainError`` while still discriminating on the specific fault when
it matters. A signature that cannot be normalised is operationally very different
from a mint that reverted, so each gets a concrete type.

Nothing here ever carries a private key, a raw signing secret or a credential in
its message — the same discipline ``docs/AGENTS.md`` mandates for logging.
"""

from __future__ import annotations


class ChainError(Exception):
    """Base class for every signing / anchoring failure in :mod:`app.chain`."""


class SignerError(ChainError):
    """A digest or transaction could not be signed, or the signature is unusable.

    Covers a Key Vault sign call failing, a returned ``(r, s)`` that recovers to no
    known public key, and a misconfigured signer selection (e.g. the tests-only
    :class:`~app.chain.signer.LocalSigner` reached for in production).
    """


class AnchorError(ChainError):
    """A card could not be anchored on-chain: the mint reverted or the receipt failed."""


class AnchorRowError(ChainError):
    """The ``part = 8`` anchor row could not be built from a mint result (CODEC §4.4)."""
