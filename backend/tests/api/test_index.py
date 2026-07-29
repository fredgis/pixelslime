"""Index bootstrap resilience: a partial (crash-mid-write) card must not take the
site down. It has to be skipped with a loud log line while every good card loads.
"""

from __future__ import annotations

from _api_helpers import build_card, build_multi_row_card, load_fixture_card
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.core.config import Settings
from app.core.index import bootstrap_index
from app.core.secrets import SecretProvider
from app.core.source import InMemoryCardSource
from app.main import create_app
from app.storage.blob import InMemoryBlobStore


def _client_around(source: InMemoryCardSource) -> TestClient:
    """Build the real app around a pre-seeded source (lifespan runs on ``__enter__``)."""
    settings = Settings(
        local_dev=True,
        rate_limit_capacity=10_000,
        rate_limit_refill_per_second=10_000.0,
    )
    secrets = SecretProvider(asmdb_bearer=None, admin_token=None)
    app = create_app(settings, source=source, blob=InMemoryBlobStore(), secrets=secrets)
    return TestClient(app)


async def test_partial_card_is_skipped_with_a_loud_log() -> None:
    source = InMemoryCardSource()
    source.add_card(build_card(1))
    full = source.add_partial_card(build_multi_row_card(4242), keep_rows=1)
    assert len(full) >= 2  # guard: the fixture really is multi-row

    with capture_logs() as logs:
        index = await bootstrap_index(source, None)

    assert index.contains(1)
    assert not index.contains(4242)
    assert index.size == 1
    assert index.degraded is False  # startup completed rather than aborting

    failures = [e for e in logs if e.get("event") == "card_read_failed"]
    assert failures, "the skipped card must be logged loudly, not swallowed"
    assert failures[0]["serial"] == 4242
    assert failures[0]["log_level"] == "warning"


async def test_good_multi_row_card_still_decodes() -> None:
    """A *complete* multi-row card must load fine — the skip is about the missing row."""
    source = InMemoryCardSource()
    source.add_card(build_multi_row_card(4242))

    index = await bootstrap_index(source, None)

    assert index.contains(4242)
    assert index.size == 1
    assert index.degraded is False


def test_app_boots_and_serves_despite_a_partial_card() -> None:
    source = InMemoryCardSource()
    source.add_card(load_fixture_card("mochibo"))  # serial 1, good
    source.add_partial_card(build_multi_row_card(4242), keep_rows=1)  # partial

    with _client_around(source) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"  # booted, not crashed or degraded
        assert health["cards"] == 1

        serials = {item["serial"] for item in client.get("/api/cards").json()["items"]}
        assert serials == {1}

        assert client.get("/api/cards/4242").status_code == 404
        assert client.get("/api/cards/4242/raw").status_code == 404
