"""Secret resolution: two **independent** ladders (W1 decisions).

The asmDB bearer resolves env-first, then Key Vault, else fail closed; the
``LOCAL_DEV`` gate was removed so a developer's env var and the platform's injected
secretRef travel the identical path. The admin token resolves on its *own* ladder
(env, then Key Vault, else disabled) so that env-sourcing the bearer — which skips
the Key Vault SDK entirely — never silently disarms the admin endpoint. A disabled
admin state is always logged loudly at startup, never silent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from structlog.testing import capture_logs

from app.core import secrets as secrets_mod
from app.core.config import Settings
from app.core.secrets import SecretError, load_secrets

_SECRET_ENV = (
    "ASMDB_BEARER_TOKEN",
    "ADMIN_TOKEN",
    "ASMDB_BASE_URL",
    "KEY_VAULT_URI",
    "KEY_VAULT_NAME",
    "ADMIN_TOKEN_SECRET_NAME",
)
_AdminResult = tuple[str | None, str]


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SECRET_ENV:
        monkeypatch.delenv(name, raising=False)


def _stub_admin_kv(result: _AdminResult) -> Callable[[str, str], Awaitable[_AdminResult]]:
    async def _inner(vault_url: str, secret_name: str) -> _AdminResult:
        await asyncio.sleep(0)
        return result

    return _inner


def _boom(message: str) -> Callable[..., Awaitable[Any]]:
    async def _inner(*_args: Any, **_kwargs: Any) -> Any:
        await asyncio.sleep(0)
        raise AssertionError(message)

    return _inner


async def test_env_bearer_wins_without_local_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ASMDB_BEARER_TOKEN", "bearer-xyz")

    provider = await load_secrets(Settings(local_dev=False))

    assert provider.asmdb_bearer_for_client() == "bearer-xyz"
    assert provider.admin_enabled is False


async def test_env_admin_token_arms_the_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ASMDB_BEARER_TOKEN", "bearer-xyz")
    monkeypatch.setenv("ADMIN_TOKEN", "let-me-in")

    provider = await load_secrets(Settings(local_dev=False))

    assert provider.admin_enabled is True
    assert provider.verify_admin("let-me-in") is True
    assert provider.verify_admin("nope") is False


async def test_fails_closed_when_nothing_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    with pytest.raises(SecretError):
        await load_secrets(Settings(local_dev=False))


async def test_fakes_need_no_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    provider = await load_secrets(Settings(local_dev=True))  # no asmDB URL ⇒ fakes

    assert provider.asmdb_bearer_for_client() is None
    assert provider.admin_enabled is False


async def test_admin_token_is_decoupled_from_the_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ASMDB_BEARER_TOKEN", "bearer-xyz")  # bearer via env, no SDK call
    monkeypatch.setenv("KEY_VAULT_URI", "https://kv.vault.azure.net/")
    monkeypatch.setenv("ADMIN_TOKEN_SECRET_NAME", "admin-tok")
    monkeypatch.setattr(secrets_mod, "_read_bearer_from_key_vault", _boom("bearer touched KV"))
    monkeypatch.setattr(
        secrets_mod, "_read_admin_from_key_vault", _stub_admin_kv(("kv-admin", "key-vault"))
    )

    with capture_logs() as logs:
        provider = await load_secrets(Settings(local_dev=False))

    assert provider.asmdb_bearer_for_client() == "bearer-xyz"  # env path, Key Vault untouched
    assert provider.admin_enabled is True  # admin armed via Key Vault, independently
    assert provider.verify_admin("kv-admin") is True
    assert any(
        e["event"] == "admin_generation_enabled" and e.get("source") == "key-vault" for e in logs
    )


async def test_admin_disabled_is_logged_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ASMDB_BEARER_TOKEN", "bearer-xyz")  # bearer fine; admin unconfigured

    with capture_logs() as logs:
        provider = await load_secrets(Settings(local_dev=False))

    assert provider.admin_enabled is False
    disabled = [e for e in logs if e["event"] == "admin_generation_disabled"]
    assert disabled, "a disabled admin endpoint must announce itself at startup"
    assert disabled[0]["log_level"] == "warning"


async def test_admin_kv_missing_secret_disables_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("ASMDB_BEARER_TOKEN", "bearer-xyz")
    monkeypatch.setenv("KEY_VAULT_URI", "https://kv.vault.azure.net/")
    monkeypatch.setenv("ADMIN_TOKEN_SECRET_NAME", "admin-tok")
    monkeypatch.setattr(
        secrets_mod,
        "_read_admin_from_key_vault",
        _stub_admin_kv((None, "admin secret 'admin-tok' not present in Key Vault")),
    )

    provider = await load_secrets(Settings(local_dev=False))

    assert provider.admin_enabled is False  # missing KV secret ⇒ disabled, not a crash


async def test_fakes_never_contact_key_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("KEY_VAULT_URI", "https://kv.vault.azure.net/")
    monkeypatch.setenv("ADMIN_TOKEN_SECRET_NAME", "admin-tok")
    monkeypatch.setattr(secrets_mod, "_read_admin_from_key_vault", _boom("fakes contacted KV"))

    provider = await load_secrets(Settings(local_dev=True))  # fakes: env only

    assert provider.admin_enabled is False
    assert provider.asmdb_bearer_for_client() is None
