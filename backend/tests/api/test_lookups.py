"""Biome / mood / companion resolution from ``contracts/lookups.json`` (W4's tables).

Ids are frozen list indices; a name is a direct index. Out-of-range ids and a clear
``has_companion`` flag resolve to ``null`` — the key is always present so the
frontend has a stable shape, not a wrong value.
"""

from __future__ import annotations

from _api_helpers import ClientFactory, load_fixture_card


def test_detail_resolves_biome_mood_companion(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    body = client.get("/api/cards/1").json()

    # mochibo: biome_id=4, mood_id=2, has_companion with companion_id=0
    assert body["biome"] == "Cozy Reading Room"
    assert body["mood"] == "Curious"
    assert body["companion"] == "Sleepy Puff Cat"


def test_companion_null_when_flag_clear(make_client: ClientFactory) -> None:
    card = load_fixture_card("worstcase-unseen")  # serial 900, has_companion=False
    client, _source, _blob = make_client(cards=[card])
    body = client.get(f"/api/cards/{card.serial}").json()

    assert body["companion"] is None  # key present, value null
    assert body["biome"] == "Starlit Rooftop"  # biome_id=11
    assert body["mood"] == "Bashful"  # mood_id=6


def test_out_of_range_ids_are_null(make_client: ClientFactory) -> None:
    card = load_fixture_card("worstcase-maxlen")  # serial 65535, biome/mood id 255
    client, _source, _blob = make_client(cards=[card])
    body = client.get(f"/api/cards/{card.serial}").json()

    assert body["biome"] is None
    assert body["mood"] is None
    assert body["companion"] == "Sleepy Puff Cat"  # has_companion, companion_id=0


def test_raw_decoded_carries_the_same_labels(make_client: ClientFactory) -> None:
    """The provenance panel's decoded card is the same projection as the detail route."""
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    decoded = client.get("/api/cards/1/raw").json()["decoded"]
    assert decoded["biome"] == "Cozy Reading Room"
    assert decoded["companion"] == "Sleepy Puff Cat"
