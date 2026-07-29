"""Pytest fixtures for the API test package.

The ``make_client`` factory builds the real app around an in-memory asmDB and blob
fake so every route is exercised end-to-end — lifespan included — with no Azure and
no network. Shared helpers live in ``_api_helpers`` (which also fixes ``sys.path``).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest
from _api_helpers import ClientFactory, load_fixture_card
from fastapi.testclient import TestClient

from app.codec import Card
from app.core.config import Settings
from app.core.secrets import SecretProvider
from app.core.source import InMemoryCardSource
from app.main import create_app
from app.storage.blob import InMemoryBlobStore


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    """Return a factory that builds an app+client around in-memory fakes.

    Each call seeds the given ``cards``, wires an optional admin token, and enters
    the client's context so the lifespan runs (building the index). Every client is
    closed at teardown.
    """
    opened: list[TestClient] = []

    def _make(
        *,
        cards: Iterable[Card] = (),
        admin_token: str | None = None,
        awake: bool = True,
        trust_forwarded_for: bool = True,
        rate_capacity: int = 10_000,
        rate_refill: float = 10_000.0,
    ) -> tuple[TestClient, InMemoryCardSource, InMemoryBlobStore]:
        source = InMemoryCardSource(awake=awake)
        blob = InMemoryBlobStore()
        for card in cards:
            source.add_card(card)
            blob.seed_card(
                card.serial,
                f"PNG-{card.serial}".encode(),
                f"WEBP-{card.serial}".encode(),
            )
        settings = Settings(
            local_dev=True,
            rate_limit_capacity=rate_capacity,
            rate_limit_refill_per_second=rate_refill,
            trust_forwarded_for=trust_forwarded_for,
        )
        secrets = SecretProvider(asmdb_bearer=None, admin_token=admin_token)
        app = create_app(settings, source=source, blob=blob, secrets=secrets)
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return client, source, blob

    yield _make

    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    """A ready client seeded with the single mochibo card (serial 1)."""
    test_client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    return test_client
