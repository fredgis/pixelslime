"""Secret loading and holding — the one place credentials live.

``docs/AGENTS.md`` is categorical: read secrets from Key Vault via
``DefaultAzureCredential`` at startup, hold them in memory, never write them to
disk, never return them in a response, never log them. This module is the only
thing that reads the asmDB bearer and the admin token, and it hands neither back
out: the bearer is used exactly once to build the asmDB client, and the admin
token is only ever *compared* — in constant time — inside
:meth:`SecretProvider.verify_admin`.

The two secrets resolve on **independent** ladders, because they differ in
criticality: the bearer is required, the admin token is optional.

asmDB bearer (required — fail *closed*):

1. ``ASMDB_BEARER_TOKEN`` from the environment whenever present. In production
   Container Apps resolves the Key Vault ``secretRef`` into this env var before the
   process starts, so the boot path makes no SDK call and cannot be tripped by a
   momentarily-unreachable vault. Locally a developer sets the same var.
2. Otherwise Key Vault directly via ``DefaultAzureCredential`` using ``KEY_VAULT_URI``.
3. Otherwise fail closed — refuse to start rather than serve unauthenticated.

Admin token (optional — fail *safe*, never crash the site over it):

1. ``ADMIN_TOKEN`` from the environment, if present.
2. Otherwise Key Vault (``KEY_VAULT_URI`` + ``ADMIN_TOKEN_SECRET_NAME``) if both are
   configured. Because the bearer usually comes from the environment, this is
   typically the only boot-time Key Vault read — and a missing secret or an
   unreachable vault *disables* the endpoint rather than downing the public read
   path.
3. Otherwise the endpoint is disabled.

Either way the admin state is logged with exactly one explicit line at startup
(``admin_generation_enabled`` / ``admin_generation_disabled`` with a reason), so a
disabled control is never a silent state. Disabled always means the route returns
401; it is never left unguarded.

``LOCAL_DEV`` / ``FAKE_BACKEND`` only select the in-memory backend; in that mode
both secrets simply read the environment and no Key Vault call is made.
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


async def _read_bearer_from_key_vault(vault_url: str, secret_name: str) -> str:
    """Fetch the required asmDB bearer from Key Vault; a failure here fails startup.

    The bearer is non-optional, so any error (vault unreachable, secret missing)
    propagates and aborts boot — better a loud failed startup than a service that
    silently cannot talk to asmDB.
    """
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient

    async with (
        DefaultAzureCredential() as credential,
        SecretClient(vault_url=vault_url, credential=credential) as client,
    ):
        secret = await client.get_secret(secret_name)
    value = secret.value
    if value is None:
        raise SecretError("asmDB bearer secret in Key Vault has no value")
    _log.info("bearer_from_key_vault")
    return value


async def _read_admin_from_key_vault(vault_url: str, secret_name: str) -> tuple[str | None, str]:
    """Fetch the *optional* admin token from Key Vault, returning ``(token, reason)``.

    Never raises: the admin endpoint is optional, so a missing secret or an
    unreachable vault disables it (``None`` plus a short reason) instead of taking
    the public read path down. The reason is a non-secret string for the startup log.
    """
    from azure.core.exceptions import AzureError, ResourceNotFoundError
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient

    try:
        async with (
            DefaultAzureCredential() as credential,
            SecretClient(vault_url=vault_url, credential=credential) as client,
        ):
            secret = await client.get_secret(secret_name)
            value = secret.value
    except ResourceNotFoundError:
        return None, f"admin secret {secret_name!r} not present in Key Vault"
    except AzureError as exc:
        _log.warning("admin_secret_unreadable", error=type(exc).__name__)
        return None, "admin secret could not be read from Key Vault"
    if value is None:
        return None, f"admin secret {secret_name!r} in Key Vault has no value"
    return value, "key-vault"


async def _resolve_admin_token(settings: Settings, env_admin: str | None) -> tuple[str | None, str]:
    """Admin-token ladder, independent of how the bearer was sourced.

    Env first, then Key Vault (only when both the vault URI and the secret name are
    configured), else disabled.
    """
    if env_admin:
        return env_admin, "env"
    if settings.key_vault_url is not None and settings.admin_token_secret_name:
        return await _read_admin_from_key_vault(
            settings.key_vault_url, settings.admin_token_secret_name
        )
    return None, "no ADMIN_TOKEN in the environment and no Key Vault admin secret configured"


def _announce_admin_state(admin_token: str | None, reason: str) -> None:
    """Log exactly one explicit line about the admin endpoint, so it is never silent."""
    if admin_token is None:
        _log.warning("admin_generation_disabled", reason=reason)
    else:
        _log.info("admin_generation_enabled", source=reason)


async def load_secrets(settings: Settings) -> SecretProvider:
    """Resolve the two secrets on independent ladders (see the module docstring).

    The bearer fails closed (no bearer ⇒ refuse to start); the admin token fails
    safe (unresolved ⇒ disabled and logged, never a crash). In fakes mode both
    secrets simply read the environment and Key Vault is never contacted.
    """
    env_bearer = os.environ.get(_ASMDB_BEARER_ENV)
    env_admin = os.environ.get(_ADMIN_TOKEN_ENV)

    if settings.use_fakes:
        _announce_admin_state(env_admin, "env" if env_admin else "fakes: no ADMIN_TOKEN set")
        return SecretProvider(asmdb_bearer=env_bearer, admin_token=env_admin)

    bearer = env_bearer
    if bearer is None:
        vault_url = settings.key_vault_url
        if vault_url is None:
            raise SecretError(
                "asmDB bearer unavailable: set ASMDB_BEARER_TOKEN, or "
                "KEY_VAULT_URI / KEY_VAULT_NAME"
            )
        bearer = await _read_bearer_from_key_vault(vault_url, settings.asmdb_secret_name)
    else:
        _log.info("bearer_from_env")

    admin_token, admin_reason = await _resolve_admin_token(settings, env_admin)
    _announce_admin_state(admin_token, admin_reason)

    return SecretProvider(asmdb_bearer=bearer, admin_token=admin_token)
