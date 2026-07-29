"""Environment-driven configuration for the PixelSlime backend.

Every value comes from an environment variable, mirroring what
``infra/modules/container-apps.bicep`` injects into the Container App. There are
**no defaults that look like a credential** — the only defaults here are resource
*names* (``asmdb-bearer-token`` is a Key Vault *secret name*, not a secret) and
operational knobs (rate-limit sizing, container names). Secret *values* are never
read here; that is :mod:`app.core.secrets`' job.

The one deliberate convenience is ``fake_backend``: when a developer sets
``LOCAL_DEV=1`` without pointing at a real asmDB, the app boots against in-memory
fakes so the whole surface can be exercised offline, exactly as W6 does with its
mock server.
"""

from __future__ import annotations

from functools import cached_property

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view over the process environment. Constructed once at startup."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    # ── asmDB (source of truth; only touched off the hot path) ──────────────
    asmdb_base_url: str | None = Field(
        default=None,
        validation_alias="ASMDB_BASE_URL",
        description="Scheme+host of the asmDB service, e.g. https://www.asmdb.cloud",
    )
    asmdb_instance: str | None = Field(
        default=None,
        validation_alias="ASMDB_INSTANCE",
        description="The asmDB instance id appended as /db/<instance>.",
    )
    asmdb_secret_name: str = Field(
        default="asmdb-bearer-token",
        validation_alias="ASMDB_SECRET_NAME",
        description="Key Vault secret NAME (not value) holding the asmDB bearer.",
    )

    # ── Key Vault (source of the bearer + admin token) ──────────────────────
    key_vault_uri: str | None = Field(
        default=None,
        validation_alias="KEY_VAULT_URI",
        description="Full vault URI, e.g. https://kv-x.vault.azure.net/",
    )
    key_vault_name: str | None = Field(
        default=None,
        validation_alias="KEY_VAULT_NAME",
        description="Vault name; used to derive the URI when KEY_VAULT_URI is absent.",
    )

    # ── Blob Storage (private; everything is proxied) ───────────────────────
    storage_account_name: str | None = Field(
        default=None,
        validation_alias="STORAGE_ACCOUNT_NAME",
    )
    blob_endpoint: str | None = Field(
        default=None,
        validation_alias="STORAGE_BLOB_ENDPOINT",
        description="Explicit blob endpoint override; derived from the account otherwise.",
    )
    cards_container: str = Field(default="cards", validation_alias="STORAGE_CARDS_CONTAINER")
    thumbs_container: str = Field(default="thumbs", validation_alias="STORAGE_THUMBS_CONTAINER")
    assets_container: str = Field(default="assets", validation_alias="STORAGE_ASSETS_CONTAINER")
    index_blob_name: str = Field(default="index.json", validation_alias="INDEX_BLOB_NAME")

    # ── Observability ───────────────────────────────────────────────────────
    applicationinsights_connection_string: str | None = Field(
        default=None,
        validation_alias="APPLICATIONINSIGHTS_CONNECTION_STRING",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # ── Admin trigger (off unless the secret is configured) ─────────────────
    admin_token_secret_name: str | None = Field(
        default=None,
        validation_alias="ADMIN_TOKEN_SECRET_NAME",
        description="Key Vault secret NAME for the manual-trigger token. Unset ⇒ endpoint off.",
    )

    # ── Rate limiting (a public site must not be trivially hammered) ─────────
    rate_limit_capacity: int = Field(
        default=120,
        ge=1,
        validation_alias="RATE_LIMIT_CAPACITY",
        description="Token-bucket burst size per client IP.",
    )
    rate_limit_refill_per_second: float = Field(
        default=2.0,
        gt=0,
        validation_alias="RATE_LIMIT_REFILL_PER_SECOND",
        description="Sustained requests per second per client IP.",
    )
    trust_forwarded_for: bool = Field(
        default=True,
        validation_alias="TRUST_FORWARDED_FOR",
        description="Behind Container Apps ingress the real client IP is in X-Forwarded-For.",
    )

    # ── SPA hosting ─────────────────────────────────────────────────────────
    frontend_dist: str | None = Field(
        default=None,
        validation_alias="FRONTEND_DIST",
        description="Path to the built SPA; defaults to ../frontend/dist relative to the repo.",
    )

    # ── Local development ───────────────────────────────────────────────────
    local_dev: bool = Field(
        default=False,
        validation_alias="LOCAL_DEV",
        description="Boot against in-memory fakes when no asmDB URL is set (offline dev).",
    )
    fake_backend: bool = Field(
        default=False,
        validation_alias=AliasChoices("PIXELSLIME_FAKE_BACKEND", "FAKE_BACKEND"),
        description="Boot against in-memory asmDB + blob fakes seeded from contracts/cards.",
    )
    index_refresh_seconds: float = Field(
        default=300.0,
        gt=0,
        validation_alias="INDEX_REFRESH_SECONDS",
        description="Reconcile cadence so a freshly bloomed card appears without a restart.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def asmdb_url(self) -> str | None:
        """Return the fully-qualified asmDB instance URL, or ``None`` if unset.

        ``base`` and ``instance`` are kept as two settings (as the task requires)
        but joined here into the single ``…/db/<instance>`` URL the client wants.
        """
        if self.asmdb_base_url is None:
            return None
        base = self.asmdb_base_url.rstrip("/")
        if self.asmdb_instance:
            return f"{base}/db/{self.asmdb_instance.strip('/')}"
        return base

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def key_vault_url(self) -> str | None:
        """Prefer an explicit URI; otherwise derive it from the vault name."""
        if self.key_vault_uri:
            return self.key_vault_uri.rstrip("/") + "/"
        if self.key_vault_name:
            return f"https://{self.key_vault_name}.vault.azure.net/"
        return None

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def blob_service_url(self) -> str | None:
        """Return the blob service endpoint, from an override or the account name."""
        if self.blob_endpoint:
            return self.blob_endpoint.rstrip("/")
        if self.storage_account_name:
            return f"https://{self.storage_account_name}.blob.core.windows.net"
        return None

    @property
    def use_fakes(self) -> bool:
        """Decide whether to boot the in-memory backend.

        Explicit opt-in via ``fake_backend`` always wins; otherwise we fall back
        to fakes only in local dev when no real asmDB URL is configured, so a
        misconfigured production never silently serves stub data.
        """
        if self.fake_backend:
            return True
        return self.local_dev and self.asmdb_url is None


def load_settings() -> Settings:
    """Read settings from the environment. Factored out so tests can override."""
    return Settings()
