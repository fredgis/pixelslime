"""Chain-layer configuration, kept separate from :mod:`app.core.config`.

The on-chain layer has its own environment surface (an RPC endpoint, the deployed
contract addresses, and the *name* of the Key Vault signing key) that the public
read path never touches. Keeping it in its own ``BaseSettings`` means the rest of
the backend does not grow chain knobs it never reads, and the chain layer can be
exercised — or left entirely dormant — without perturbing anything else.

As in :mod:`app.core.config`, **no default here looks like a credential**: the
only values are an RPC URL, a chain id, resource *names* and addresses. The
signing key itself lives in Key Vault and is referenced purely by name.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Polygon Amoy testnet — the settled chain choice (docs/PLAN.md §8.7).
AMOY_CHAIN_ID = 80002


class ChainSettings(BaseSettings):
    """Typed view over the chain-related environment. Constructed on demand."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    rpc_url: str | None = Field(
        default=None,
        validation_alias="CHAIN_RPC_URL",
        description="JSON-RPC endpoint for the target chain (Amoy in production).",
    )
    chain_id: int = Field(
        default=AMOY_CHAIN_ID,
        validation_alias="CHAIN_ID",
        description="EIP-155 chain id; 80002 is Polygon Amoy.",
    )

    # ── Key Vault signing key (the secp256k1 anchor/minter key) ─────────────
    key_vault_uri: str | None = Field(
        default=None,
        validation_alias="KEY_VAULT_URI",
        description="Vault URI holding the secp256k1 signing key (shared with app.core).",
    )
    signer_key_name: str | None = Field(
        default=None,
        validation_alias="CHAIN_SIGNER_KEY_NAME",
        description="Key Vault EC key NAME (curve P-256K) used to sign mintCard txs.",
    )
    signer_key_version: str | None = Field(
        default=None,
        validation_alias="CHAIN_SIGNER_KEY_VERSION",
        description="Optional pinned key version; latest is used when unset.",
    )

    # ── Deployed contract addresses ─────────────────────────────────────────
    card_address: str | None = Field(
        default=None,
        validation_alias="CARD_CONTRACT_ADDRESS",
        description="Deployed PixelSlimeCard address (the anchor target).",
    )

    # ── Tests-only local signer escape hatch (never armed in production) ────
    allow_local_signer: bool = Field(
        default=False,
        validation_alias="CHAIN_ALLOW_LOCAL_SIGNER",
        description="Tests only: permit the env-key LocalSigner. Must be false in prod.",
    )
    local_private_key: str | None = Field(
        default=None,
        validation_alias="CHAIN_LOCAL_PRIVATE_KEY",
        description="Tests only: hex private key for LocalSigner. Never set in prod.",
    )


def load_chain_settings() -> ChainSettings:
    """Read chain settings from the environment. Factored out so tests can override."""
    return ChainSettings()
