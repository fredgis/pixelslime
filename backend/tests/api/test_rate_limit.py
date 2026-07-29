"""Rate-limiting behaviour: the bucket empties, and /api/health is exempt."""

from __future__ import annotations

from _api_helpers import ClientFactory, load_fixture_card


def test_rate_limit_kicks_in(make_client: ClientFactory) -> None:
    # Tiny bucket, negligible refill: the fourth call within the burst is rejected.
    client, _source, _blob = make_client(
        cards=[load_fixture_card("mochibo")], rate_capacity=3, rate_refill=0.001
    )
    statuses = [client.get("/api/cards").status_code for _ in range(5)]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses
    limited = client.get("/api/cards")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1


def test_health_is_exempt_from_rate_limit(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(
        cards=[load_fixture_card("mochibo")], rate_capacity=1, rate_refill=0.001
    )
    # Drain the bucket on a normal route first.
    client.get("/api/cards")
    client.get("/api/cards")
    # Health must still answer regardless of the bucket state.
    for _ in range(5):
        assert client.get("/api/health").status_code == 200
