"""Tests for health, stats and ERC-721 metadata routes."""

from __future__ import annotations

from _api_helpers import ClientFactory, build_card, load_fixture_card


def test_health_ok_when_source_awake(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["cards"] == 1
    assert body["engine"] == "asmdb-fake/1.0"


def test_health_degraded_when_source_asleep(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[], awake=False)
    body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["cards"] == 0


def test_stats_counts_and_economy(make_client: ClientFactory) -> None:
    cards = [
        build_card(1, rarity="COMMON", type_="WATER"),
        build_card(2, rarity="MYTHIC", type_="COSMIC"),
    ]
    client, _source, _blob = make_client(cards=cards)
    body = client.get("/api/stats").json()

    assert body["total"] == 2
    assert body["byRarity"]["COMMON"] == 1
    assert body["byRarity"]["MYTHIC"] == 1
    assert body["byType"]["WATER"] == 1
    assert body["genesisRemaining"] == 365_000 - 2 * 100
    assert body["bloomsRemaining"] == 3_650 - 2


def test_nft_metadata_shape(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    body = client.get("/api/nft/1").json()

    assert set(body) >= {"name", "description", "image", "attributes"}
    assert body["image"].startswith("http://testserver/api/cards/1/image")
    assert isinstance(body["attributes"], list)
    trait_types = {attr["trait_type"] for attr in body["attributes"]}
    assert {"Rarity", "Type", "Level"} <= trait_types


def test_nft_404_for_unknown_serial(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    assert client.get("/api/nft/55").status_code == 404
