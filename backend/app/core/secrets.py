"""Secret loading and holding — the one place credentials live.

``docs/AGENTS.md`` is categorical: read secrets from Key Vault via
``DefaultAzureCredential`` at startup, hold them in memory, never write them to
disk, never return them in a response, never log them. This module is the only
thing that reads the asmDB bearer and the admin token, and it hands neither back
out: the bearer is used exactly once to build the asmDB client, and the admin
token is only ever *compared* — in constant time — inside :meth:`SecretProvider.verify_admin`.

Secrets resolve in a fixed order (W1's Bicep wires both mechanisms):

1. ``ASMDB_BEARER_TOKEN`` (and, if the admin endpoint is enabled, ``ADMIN_TOKEN``)
   straight from the environment **whenever the bearer is present**. In production
   Container Apps has already resolved the Key Vault ``secretRef`` into the env var
   using the managed identity before the process starts, so the boot path makes no
   SDK call and cannot be tripped by a momentarily-unreachable vault. Locally a
   developer sets the same vars — the *same* code path, deliberately.
2. Otherwise, read from Key Vault directly via ``DefaultAzureCredential`` using
   ``KEY_VAULT_URI`` — the fallback for any host that does not pre-inject secrets.
3. Otherwise fail closed with a clear error.

``LOCAL_DEV`` / ``FAKE_BACKEND`` only select the in-memory backend; they no longer
gate where the bearer comes from.
"""

from __future__ import annotations

import os
import secrets as _secrets

from .config import Settings
from .logging import get_logger

_log = get_logger(__name__)

_ADMIN_TOKEN_ENV = "ADMIN_TOKEN"  # noqa: S105 - env var NAME, not a secret value
_ASMDB_BEARER_ENV = "ASMDB_BEARER_TOKEN"


class SecretError(RuntimeError):
    """Raised when a required secret cannot be sourced. Never carries the value."""


class SecretProvider:
    """Holds the loaded secrets in memory and exposes only safe operations.

    Neither secret is retrievable as a plain string through a method that a route
    could accidentally return: the bearer is consumed once at wiring time via
    :meth:`asmdb_bearer_for_client`, and the admin token is only compared.
    """

    def __init__(self, *, asmdb_bearer: str | None, admin_token: str | None) -> None:
        self._asmdb_bearer = asmdb_bearer or None
        self._admin_token = admin_token or None

    @property
    def admin_enabled(self) -> bool:
        """Whether ``/api/admin/generate`` is armed (a token was configured)."""
        return self._admin_token is not None

    def asmdb_bearer_for_client(self) -> str | None:
        """Return the bearer for building the asmDB client. Wiring-only.

        This is deliberately *not* a property and is never referenced by any route;
        it exists so :func:`app.main.create_app` can hand the token to the asmDB
        client and nowhere else.
        """
        return self._asmdb_bearer

    def verify_admin(self, presented: str | None) -> bool:
        """Constant-time compare of a presented header against the admin token.

        Returns ``False`` when the endpoint is disabled (no token configured) or the
        header is missing, and uses :func:`secrets.compare_digest` so a wrong token
        cannot be discovered by timing.
        """
        if self._admin_token is None or presented is None:
            return False
        return _secrets.compare_digest(presented.encode("utf-8"), self._admin_token.encode("utf-8"))


def _from_env(settings: Settings) -> SecretProvider:
    """Source both secrets from environment variables — the primary path.

    In production Container Apps resolves the Key Vault ``secretRef`` for the bearer
    (and ``ADMIN_TOKEN`` when the admin endpoint is enabled) into the environment
    before startup; locally a developer sets the same vars. Either way there is no
    Key Vault SDK call on the boot path.
    """
    bearer = os.environ.get(_ASMDB_BEARER_ENV)
    admin = os.environ.get(_ADMIN_TOKEN_ENV)
    _log.info(
        "secrets_from_env",
        asmdb_bearer_present=bearer is not None,
        admin_token_present=admin is not None,
    )
    return SecretProvider(asmdb_bearer=bearer, admin_token=admin)


async def _from_key_vault(settings: Settings) -> SecretProvider:
    """Source secrets from Key Vault using the managed identity, at startup."""
    if settings.key_vault_url is None:
        raise SecretError("KEY_VAULT_URI or KEY_VAULT_NAME must be set to read from Key Vault")

    # Imported lazily so the fake/local path never needs the Azure SDK installed.
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient

    async with (
        DefaultAzureCredential() as credential,
        SecretClient(vault_url=settings.key_vault_url, credential=credential) as client,
    ):
        bearer_secret = await client.get_secret(settings.asmdb_secret_name)
        admin_token: str | None = None
        if settings.admin_token_secret_name:
            try:
                admin_secret = await client.get_secret(settings.admin_token_secret_name)
                admin_token = admin_secret.value
            except ResourceNotFoundError:
                _log.info("admin_secret_absent", secret_name=settings.admin_token_secret_name)
    _log.info("secrets_from_key_vault", admin_enabled=admin_token is not None)
    return SecretProvider(asmdb_bearer=bearer_secret.value, admin_token=admin_token)


async def load_secrets(settings: Settings) -> SecretProvider:
    """Resolve secrets: env bearer first, then Key Vault, then fail closed.

    The fake backend needs no real bearer, so it short-circuits to the (optional)
    env values. Otherwise a bearer already in the environment wins — this is both
    the production path (Container Apps injected it from Key Vault before startup,
    so no SDK call) and the local path. Only a host that pre-injects nothing reads
    Key Vault directly; if even that is unconfigured we refuse to start rather than
    serve unauthenticated against asmDB.
    """
    if settings.use_fakes:
        return _from_env(settings)
    if os.environ.get(_ASMDB_BEARER_ENV):
        return _from_env(settings)
    if settings.key_vault_url is not None:
        return await _from_key_vault(settings)
    raise SecretError(
        "asmDB bearer unavailable: set ASMDB_BEARER_TOKEN, or KEY_VAULT_URI / KEY_VAULT_NAME"
    )
