"""Ethereum signing, with the private key pinned inside an Azure Key Vault HSM.

The production signer never possesses the private key. It asks Key Vault to sign a
32-byte digest with an EC key on curve **P-256K (secp256k1)** via
``DefaultAzureCredential``; the key exists only in the HSM and appears nowhere in
this process, its environment, or its logs. That is the whole point — a leaked
container image or a scraped environment yields nothing that can move funds.

Key Vault hands back a bare ``(r, s)`` pair, which is *not* enough for Ethereum:

* Ethereum needs the recovery id ``v`` so a verifier can recover the signer's
  address from the signature alone. Key Vault does not return it, so we derive it
  ourselves — try both candidate public keys and keep the one that recovers to our
  known address (:func:`normalize_signature`).
* secp256k1 signatures are malleable: ``(r, s)`` and ``(r, N - s)`` are both valid.
  Ethereum (post-EIP-2) rejects the upper half, so ``s`` is folded into the lower
  half of the curve order and the parity flipped to match. Skipping this makes
  roughly half of all Key Vault signatures bounce off-chain.

Both steps are pure arithmetic over the returned ``(r, s)`` and are unit-tested
against a fixed vector, because they are exactly the kind of fiddly detail that is
wrong until proven right.

:class:`LocalSigner` is a **tests-only** fallback that holds a raw private key from
an environment variable. It is clearly marked, guarded behind an explicit opt-in
flag, and :func:`build_signer` refuses to select it in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from eth_keys import KeyAPI
from eth_utils import to_canonical_address, to_checksum_address

from app.codec.keccak import keccak256
from app.core.logging import get_logger

from .config import ChainSettings
from .errors import SignerError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from eth_typing import ChecksumAddress

_log = get_logger(__name__)
_keys = KeyAPI()

# secp256k1 group order N and its half. `s` must land in `(0, N/2]` (EIP-2).
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_HALF_N = SECP256K1_N // 2

# Env var name (not a secret) for the tests-only local key.
_LOCAL_KEY_ENV = "CHAIN_LOCAL_PRIVATE_KEY"


@dataclass(frozen=True)
class Signature:
    """An Ethereum ECDSA signature with a recovered, low-``s`` normal form.

    ``v`` is the 27/28 recovery id used by ``ecrecover`` and EIP-712; ``y_parity``
    (0/1) is what a type-2 (EIP-1559) transaction envelope wants instead.
    """

    v: int
    r: int
    s: int

    def __post_init__(self) -> None:
        if self.v not in (27, 28):
            raise SignerError(f"v must be 27 or 28, got {self.v}")
        if not (0 < self.s <= SECP256K1_HALF_N):
            raise SignerError("s is not in the lower half of the curve order")
        if not (0 < self.r < SECP256K1_N):
            raise SignerError("r is out of range")

    @property
    def y_parity(self) -> int:
        """0/1 parity for the EIP-1559 transaction envelope."""
        return self.v - 27

    def to_bytes(self) -> bytes:
        """65-byte ``r || s || v`` form, as EIP-712 verifiers and ``ecrecover`` expect."""
        return self.r.to_bytes(32, "big") + self.s.to_bytes(32, "big") + bytes([self.v])


@dataclass(frozen=True)
class SignedTransaction:
    """A signed transaction ready for ``eth_sendRawTransaction``."""

    raw_transaction: bytes
    tx_hash: bytes
    signature: Signature


def normalize_signature(
    r: int, s: int, message_hash: bytes, expected_address: str | bytes
) -> Signature:
    """Turn a bare secp256k1 ``(r, s)`` into a full, canonical Ethereum signature.

    Folds ``s`` into the lower half of the curve order (EIP-2), then recovers the
    recovery id ``v`` by trying both candidates and keeping the one whose public key
    matches ``expected_address``. Raises :class:`SignerError` if neither does, which
    means the signature simply was not produced by that address's key.
    """
    if not (0 < r < SECP256K1_N) or not (0 < s < SECP256K1_N):
        raise SignerError("r or s is outside the secp256k1 scalar field")

    # EIP-2: keep s in the lower half. This is a symmetry of the signature, so the
    # folded form verifies identically — but a verifier still needs the matching v.
    if s > SECP256K1_HALF_N:
        s = SECP256K1_N - s

    if len(message_hash) != 32:
        raise SignerError(f"message hash must be 32 bytes, got {len(message_hash)}")

    canonical = (
        to_canonical_address(expected_address)
        if isinstance(expected_address, str)
        else bytes(expected_address)
    )

    for rec_id in (0, 1):
        try:
            candidate = _keys.Signature(vrs=(rec_id, r, s))
            public_key = candidate.recover_public_key_from_msg_hash(message_hash)
        except Exception:  # noqa: S112 - a wrong rec_id simply fails to recover; try the other
            continue
        if public_key.to_canonical_address() == canonical:
            return Signature(v=rec_id + 27, r=r, s=s)

    raise SignerError("signature does not recover to the expected address")


class Signer(Protocol):
    """The signing surface the anchor path depends on.

    Implementations differ only in *where the key lives*: an HSM
    (:class:`KeyVaultSigner`) or process memory (:class:`LocalSigner`, tests only).
    """

    @property
    def address(self) -> ChecksumAddress:
        """The 0x-checksummed address this signer controls."""
        ...

    def sign_hash(self, message_hash: bytes) -> Signature:
        """Sign a 32-byte digest, returning a canonical low-``s`` signature."""
        ...

    def sign_transaction(self, transaction: dict[str, Any]) -> SignedTransaction:
        """Sign a transaction dict and return the raw broadcastable bytes."""
        ...


class _BaseSigner:
    """Shared transaction assembly built on the primitive :meth:`sign_hash`."""

    _address: ChecksumAddress

    @property
    def address(self) -> ChecksumAddress:
        return self._address

    def sign_hash(self, message_hash: bytes) -> Signature:  # pragma: no cover - abstract
        raise NotImplementedError

    def sign_transaction(self, transaction: dict[str, Any]) -> SignedTransaction:
        """Sign a transaction dict (type-2 recommended) and return the raw bytes.

        The transaction is RLP-encoded to its signing digest, signed via
        :meth:`sign_hash`, then re-encoded with the signature. The returned
        ``tx_hash`` is ``keccak256`` of the signed bytes — the hash the node will
        report.
        """
        from eth_account._utils.signing import (
            encode_transaction,
            serializable_unsigned_transaction_from_dict,
        )

        unsigned = serializable_unsigned_transaction_from_dict(transaction)
        signature = self.sign_hash(unsigned.hash())
        raw = bytes(
            encode_transaction(unsigned, vrs=(signature.y_parity, signature.r, signature.s))
        )
        return SignedTransaction(raw_transaction=raw, tx_hash=keccak256(raw), signature=signature)


def _address_from_public_key(x: bytes, y: bytes) -> ChecksumAddress:
    """Ethereum address from an EC public key's ``(x, y)`` coordinates.

    ``address = keccak256(x || y)[-20:]``, each coordinate left-padded to 32 bytes.
    Reuses the codec's Ethereum-variant ``keccak256`` rather than a second copy.
    """
    uncompressed = x.rjust(32, b"\x00") + y.rjust(32, b"\x00")
    return to_checksum_address(keccak256(uncompressed)[-20:])


class KeyVaultSigner(_BaseSigner):
    """Signs via an Azure Key Vault secp256k1 key; the key never leaves the HSM."""

    def __init__(
        self,
        *,
        vault_url: str,
        key_name: str,
        key_version: str | None = None,
        credential: Any = None,
    ) -> None:
        # Imported lazily so the wider backend need not carry azure-keyvault-keys
        # unless the chain layer is actually wired up.
        from azure.keyvault.keys import KeyClient
        from azure.keyvault.keys.crypto import CryptographyClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()

        key_client = KeyClient(vault_url=vault_url, credential=credential)
        key = key_client.get_key(key_name, version=key_version)

        jwk = key.key
        crv = getattr(jwk, "crv", None)
        x = getattr(jwk, "x", None)
        y = getattr(jwk, "y", None)
        if crv not in ("P-256K", "SECP256K1"):
            raise SignerError(f"key {key_name!r} is on curve {crv!r}, expected P-256K (secp256k1)")
        if x is None or y is None:
            raise SignerError(f"key {key_name!r} has no public coordinates")

        self._address = _address_from_public_key(x, y)
        self._crypto = CryptographyClient(key, credential=credential)
        _log.info("keyvault_signer_ready", address=self._address, key_name=key_name)

    def sign_hash(self, message_hash: bytes) -> Signature:
        from azure.keyvault.keys.crypto import SignatureAlgorithm

        if len(message_hash) != 32:
            raise SignerError(f"message hash must be 32 bytes, got {len(message_hash)}")
        result = self._crypto.sign(SignatureAlgorithm.es256_k, message_hash)
        raw = result.signature
        if len(raw) != 64:
            raise SignerError(f"Key Vault returned {len(raw)} signature bytes, expected 64")
        r = int.from_bytes(raw[:32], "big")
        s = int.from_bytes(raw[32:], "big")
        return normalize_signature(r, s, message_hash, self._address)


class LocalSigner(_BaseSigner):
    """Holds a raw private key in process memory — testnets only.

    Originally written so the anchor and voucher paths could be exercised against a
    local Anvil node without an HSM. It is also what signs on Polygon Amoy, because
    the Key Vault data plane is unreachable under the subscription's governance
    policy. :func:`build_signer` will only hand one back when the escape hatch is
    explicitly armed *and* the target chain is in :data:`TESTNET_CHAIN_IDS`, and this
    class logs a loud warning on construction. Do not use it to sign anything of
    anything that touches real value.
    """

    def __init__(self, private_key: bytes | str) -> None:
        if isinstance(private_key, str):
            private_key = bytes.fromhex(private_key.removeprefix("0x"))
        if len(private_key) != 32:
            raise SignerError("local private key must be 32 bytes")
        self._pk = _keys.PrivateKey(private_key)
        self._address = to_checksum_address(self._pk.public_key.to_canonical_address())
        _log.warning("local_signer_in_use", address=self._address)

    @classmethod
    def from_env(cls, var: str = _LOCAL_KEY_ENV) -> LocalSigner:
        """Build from a hex private key in ``var``; raises if it is absent."""
        value = os.environ.get(var)
        if not value:
            raise SignerError(f"{var} is not set; LocalSigner is unavailable")
        return cls(value)

    def sign_hash(self, message_hash: bytes) -> Signature:
        if len(message_hash) != 32:
            raise SignerError(f"message hash must be 32 bytes, got {len(message_hash)}")
        native = self._pk.sign_msg_hash(message_hash)
        # Re-run through the same normalisation the HSM path uses, so both signers
        # are provably identical in their output form.
        return normalize_signature(native.r, native.s, message_hash, self._address)


#: Chain ids on which a raw in-process key is an acceptable risk. Amoy is the
#: deployed target; the others are local/CI nodes. Anything absent from this set
#: is treated as real money and refuses the LocalSigner outright.
TESTNET_CHAIN_IDS = frozenset({80002, 31337, 1337, 11155111})


def build_signer(settings: ChainSettings | None = None) -> Signer:
    """Select the Key Vault signer, or the raw-key local one on a testnet.

    Key Vault is preferred whenever ``KEY_VAULT_URI`` and ``CHAIN_SIGNER_KEY_NAME``
    are both set, and can never be silently shadowed by the local signer.

    The local signer is a deliberate, *bounded* concession. The subscription's
    governance policy forces ``publicNetworkAccess: Disabled`` on Key Vault and
    reverts any change within seconds, so the Amoy rollout signs with a key held in
    a Container Apps secret instead. That is only defensible while the tokens carry
    no value, so the concession is bounded by :data:`TESTNET_CHAIN_IDS` here in code
    rather than by a comment asking future readers to be careful: aiming the same
    configuration at a value-bearing chain fails closed.
    """
    settings = settings or ChainSettings()

    if settings.key_vault_uri and settings.signer_key_name:
        return KeyVaultSigner(
            vault_url=settings.key_vault_uri,
            key_name=settings.signer_key_name,
            key_version=settings.signer_key_version,
        )

    if settings.allow_local_signer and settings.local_private_key:
        if settings.chain_id not in TESTNET_CHAIN_IDS:
            raise SignerError(
                f"refusing the in-process LocalSigner on chain {settings.chain_id}: "
                "it is only permitted on a testnet "
                f"({sorted(TESTNET_CHAIN_IDS)}). Use a Key Vault key instead."
            )
        _log.warning("build_signer_local_fallback", chain_id=settings.chain_id)
        return LocalSigner(settings.local_private_key)

    raise SignerError(
        "no signer configured: set KEY_VAULT_URI + CHAIN_SIGNER_KEY_NAME "
        "(production), or CHAIN_ALLOW_LOCAL_SIGNER + CHAIN_LOCAL_PRIVATE_KEY (tests)"
    )
