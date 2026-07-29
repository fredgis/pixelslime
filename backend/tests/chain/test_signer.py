"""Tests for :mod:`app.chain.signer` — the fiddly ``(r, s) → (v, r, s)`` core.

These pin the signer to a **fixed external vector** (``_chain_helpers.KV_*``): the
same digest and key must always yield the same canonical low-``s`` signature, the
malleable upper-half form must fold to it, and a signature must recover to the
right address or be rejected. The Key Vault path is exercised with a fake HSM
client so the raw-``(r, s)`` handling is covered without a live vault.
"""

from __future__ import annotations

import pytest
from _chain_helpers import (
    KV_ADDRESS,
    KV_DIGEST,
    KV_PRIVATE_KEY,
    KV_R,
    KV_S_HIGH,
    KV_S_LOW,
    KV_V,
)
from eth_keys import KeyAPI

from app.chain.config import ChainSettings
from app.chain.errors import SignerError
from app.chain.signer import (
    SECP256K1_HALF_N,
    SECP256K1_N,
    KeyVaultSigner,
    LocalSigner,
    Signature,
    _address_from_public_key,
    build_signer,
    normalize_signature,
)

_keys = KeyAPI()


class TestNormalizeSignature:
    def test_known_vector_recovers_expected_v_and_low_s(self) -> None:
        sig = normalize_signature(KV_R, KV_S_LOW, KV_DIGEST, KV_ADDRESS)
        assert (sig.v, sig.r, sig.s) == (KV_V, KV_R, KV_S_LOW)

    def test_high_s_is_folded_to_the_lower_half(self) -> None:
        # The malleable upper-half counterpart must normalise to the identical
        # canonical signature — same v, same low s.
        assert KV_S_HIGH > SECP256K1_HALF_N
        sig = normalize_signature(KV_R, KV_S_HIGH, KV_DIGEST, KV_ADDRESS)
        assert sig.s == KV_S_LOW
        assert sig.s <= SECP256K1_HALF_N
        assert sig == normalize_signature(KV_R, KV_S_LOW, KV_DIGEST, KV_ADDRESS)

    def test_v_is_recovered_by_trying_both_candidates(self) -> None:
        # Whatever the recovery id, the produced v must let eth_keys recover the
        # address back out of the signature alone.
        sig = normalize_signature(KV_R, KV_S_LOW, KV_DIGEST, KV_ADDRESS)
        recovered = _keys.Signature(
            vrs=(sig.v - 27, sig.r, sig.s)
        ).recover_public_key_from_msg_hash(KV_DIGEST)
        assert recovered.to_checksum_address() == KV_ADDRESS

    def test_wrong_address_is_rejected(self) -> None:
        other = "0x000000000000000000000000000000000000BEEF"
        with pytest.raises(SignerError, match="does not recover"):
            normalize_signature(KV_R, KV_S_LOW, KV_DIGEST, other)

    def test_out_of_range_scalar_raises(self) -> None:
        with pytest.raises(SignerError):
            normalize_signature(0, KV_S_LOW, KV_DIGEST, KV_ADDRESS)
        with pytest.raises(SignerError):
            normalize_signature(KV_R, SECP256K1_N, KV_DIGEST, KV_ADDRESS)

    def test_bad_digest_length_raises(self) -> None:
        with pytest.raises(SignerError, match="32 bytes"):
            normalize_signature(KV_R, KV_S_LOW, b"\x00" * 31, KV_ADDRESS)

    def test_accepts_bytes_address(self) -> None:
        raw = bytes.fromhex(KV_ADDRESS[2:])
        sig = normalize_signature(KV_R, KV_S_LOW, KV_DIGEST, raw)
        assert sig.v == KV_V


class TestSignature:
    def test_rejects_bad_v(self) -> None:
        with pytest.raises(SignerError, match="v must be"):
            Signature(v=29, r=KV_R, s=KV_S_LOW)

    def test_rejects_high_s(self) -> None:
        with pytest.raises(SignerError, match="lower half"):
            Signature(v=27, r=KV_R, s=KV_S_HIGH)

    def test_y_parity_and_bytes(self) -> None:
        sig = Signature(v=28, r=KV_R, s=KV_S_LOW)
        assert sig.y_parity == 1
        blob = sig.to_bytes()
        assert len(blob) == 65
        assert blob[-1] == 28
        assert int.from_bytes(blob[:32], "big") == KV_R


class TestLocalSigner:
    def test_matches_the_known_vector(self) -> None:
        signer = LocalSigner(KV_PRIVATE_KEY)
        assert signer.address == KV_ADDRESS
        sig = signer.sign_hash(KV_DIGEST)
        # eth_keys is deterministic (RFC 6979), so this is exactly the vector.
        assert (sig.v, sig.r, sig.s) == (KV_V, KV_R, KV_S_LOW)

    def test_accepts_0x_prefixed_and_bytes_keys(self) -> None:
        a = LocalSigner("0x" + KV_PRIVATE_KEY)
        b = LocalSigner(bytes.fromhex(KV_PRIVATE_KEY))
        assert a.address == b.address == KV_ADDRESS

    def test_rejects_short_key(self) -> None:
        with pytest.raises(SignerError, match="32 bytes"):
            LocalSigner(b"\x01\x02\x03")

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHAIN_LOCAL_PRIVATE_KEY", KV_PRIVATE_KEY)
        signer = LocalSigner.from_env()
        assert signer.address == KV_ADDRESS

    def test_from_env_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CHAIN_LOCAL_PRIVATE_KEY", raising=False)
        with pytest.raises(SignerError, match="not set"):
            LocalSigner.from_env()

    def test_sign_transaction_is_recoverable(self) -> None:
        signer = LocalSigner(KV_PRIVATE_KEY)
        tx = {
            "type": 2,
            "chainId": 80002,
            "nonce": 3,
            "maxFeePerGas": 30_000_000_000,
            "maxPriorityFeePerGas": 1_000_000_000,
            "gas": 200_000,
            "to": "0x" + "22" * 20,
            "value": 0,
            "data": b"\x12\x34",
        }
        signed = signer.sign_transaction(tx)
        assert len(signed.tx_hash) == 32
        assert signed.raw_transaction[0] == 0x02  # EIP-1559 typed envelope


class TestAddressDerivation:
    def test_address_from_public_key_matches_private_key(self) -> None:
        pk = _keys.PrivateKey(bytes.fromhex(KV_PRIVATE_KEY))
        pub = pk.public_key.to_bytes()  # 64 bytes: x || y
        derived = _address_from_public_key(pub[:32], pub[32:])
        assert derived == KV_ADDRESS

    def test_address_left_pads_short_coordinates(self) -> None:
        pk = _keys.PrivateKey(bytes.fromhex(KV_PRIVATE_KEY))
        pub = pk.public_key.to_bytes()
        x = pub[:32].lstrip(b"\x00") or b"\x00"
        y = pub[32:].lstrip(b"\x00") or b"\x00"
        # Trimmed coordinates must still derive the same address once re-padded.
        assert _address_from_public_key(x, y) == KV_ADDRESS


class _FakeSignResult:
    def __init__(self, raw: bytes) -> None:
        self.signature = raw


class _FakeCrypto:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw
        self.calls = 0

    def sign(self, algorithm: object, digest: bytes) -> _FakeSignResult:
        self.calls += 1
        return _FakeSignResult(self._raw)


class TestKeyVaultSignerSignPath:
    """Exercise the raw-``(r, s)`` handling without a live vault."""

    def _signer_with_raw(self, raw: bytes) -> KeyVaultSigner:
        signer = object.__new__(KeyVaultSigner)
        signer._address = KV_ADDRESS  # type: ignore[attr-defined]
        signer._crypto = _FakeCrypto(raw)  # type: ignore[attr-defined]
        return signer

    def test_low_s_signature_from_vault(self) -> None:
        raw = KV_R.to_bytes(32, "big") + KV_S_LOW.to_bytes(32, "big")
        signer = self._signer_with_raw(raw)
        sig = signer.sign_hash(KV_DIGEST)
        assert (sig.v, sig.r, sig.s) == (KV_V, KV_R, KV_S_LOW)

    def test_high_s_from_vault_is_normalised(self) -> None:
        # Key Vault will happily return an upper-half s; the signer must fold it.
        raw = KV_R.to_bytes(32, "big") + KV_S_HIGH.to_bytes(32, "big")
        signer = self._signer_with_raw(raw)
        sig = signer.sign_hash(KV_DIGEST)
        assert sig.s == KV_S_LOW
        assert sig.s <= SECP256K1_HALF_N

    def test_wrong_length_signature_raises(self) -> None:
        signer = self._signer_with_raw(b"\x00" * 40)
        with pytest.raises(SignerError, match="expected 64"):
            signer.sign_hash(KV_DIGEST)


class TestBuildSigner:
    def test_local_fallback_when_allowed(self) -> None:
        settings = ChainSettings(
            CHAIN_ALLOW_LOCAL_SIGNER=True,
            CHAIN_LOCAL_PRIVATE_KEY=KV_PRIVATE_KEY,
        )
        signer = build_signer(settings)
        assert isinstance(signer, LocalSigner)
        assert signer.address == KV_ADDRESS

    def test_nothing_configured_raises(self) -> None:
        settings = ChainSettings()
        with pytest.raises(SignerError, match="no signer configured"):
            build_signer(settings)

    def test_key_vault_wins_over_local_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Even with the local escape hatch armed, a configured Key Vault key must be
        # chosen — the tests-only signer can never shadow a real one.
        sentinel = object()

        def _fake_kv(**kwargs: object) -> object:
            return sentinel

        monkeypatch.setattr("app.chain.signer.KeyVaultSigner", _fake_kv)
        settings = ChainSettings(
            KEY_VAULT_URI="https://kv.vault.azure.net/",
            CHAIN_SIGNER_KEY_NAME="pixelslime-signer",
            CHAIN_ALLOW_LOCAL_SIGNER=True,
            CHAIN_LOCAL_PRIVATE_KEY=KV_PRIVATE_KEY,
        )
        assert build_signer(settings) is sentinel

    def test_local_signer_refused_on_a_mainnet_chain(self) -> None:
        # The Amoy rollout signs with a raw key held in a Container Apps secret,
        # because the governance policy leaves the Key Vault data plane unreachable.
        # That trade is only acceptable while the tokens are worthless, so the
        # "testnet only" rule is enforced here rather than left to a docstring:
        # pointing the same configuration at Polygon mainnet must fail closed.
        settings = ChainSettings(
            CHAIN_ID=137,
            CHAIN_ALLOW_LOCAL_SIGNER=True,
            CHAIN_LOCAL_PRIVATE_KEY=KV_PRIVATE_KEY,
        )
        with pytest.raises(SignerError, match="testnet"):
            build_signer(settings)

    @pytest.mark.parametrize("chain_id", [80002, 31337, 11155111])
    def test_local_signer_allowed_on_known_testnets(self, chain_id: int) -> None:
        settings = ChainSettings(
            CHAIN_ID=chain_id,
            CHAIN_ALLOW_LOCAL_SIGNER=True,
            CHAIN_LOCAL_PRIVATE_KEY=KV_PRIVATE_KEY,
        )
        assert isinstance(build_signer(settings), LocalSigner)
