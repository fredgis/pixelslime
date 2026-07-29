"""Tests for the gallery and single-card routes."""

from __future__ import annotations

from _api_helpers import ClientFactory, build_card, card_minted_today, load_fixture_card
from fastapi.testclient import TestClient


def test_today_returns_card_and_countdown(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[card_minted_today(serial=1)])
    response = client.get("/api/cards/today")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"card", "nextBloomAt", "secondsUntilNext", "dayNumber"}
    assert body["card"]["serial"] == 1
    assert body["dayNumber"] == 1
    assert body["secondsUntilNext"] >= 0
    assert body["nextBloomAt"].endswith("Z")


def test_today_404_when_nothing_bloomed_today(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[build_card(1, mint_day=10)])
    response = client.get("/api/cards/today")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_card_today"


def test_today_is_not_shadowed_by_serial_route(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[card_minted_today(serial=7)])
    # "today" must hit the today route, never be parsed as a serial.
    assert client.get("/api/cards/today").status_code == 200


def test_pagination_windows_and_has_more(make_client: ClientFactory) -> None:
    cards = [build_card(serial=n, mint_day=n) for n in range(1, 31)]
    client, _source, _blob = make_client(cards=cards)

    first = client.get("/api/cards", params={"page": 1, "size": 10}).json()
    assert first["total"] == 30
    assert len(first["items"]) == 10
    assert first["hasMore"] is True

    last = client.get("/api/cards", params={"page": 3, "size": 10}).json()
    assert len(last["items"]) == 10
    assert last["hasMore"] is False

    past_end = client.get("/api/cards", params={"page": 4, "size": 10}).json()
    assert past_end["items"] == []
    assert past_end["hasMore"] is False


def test_filter_by_type_and_rarity(make_client: ClientFactory) -> None:
    cards = [
        build_card(1, type_="WATER", rarity="COMMON"),
        build_card(2, type_="EMBER", rarity="COMMON"),
        build_card(3, type_="WATER", rarity="MYTHIC"),
    ]
    client, _source, _blob = make_client(cards=cards)

    water = client.get("/api/cards", params={"type": "WATER"}).json()
    assert {c["serial"] for c in water["items"]} == {1, 3}

    mythic = client.get("/api/cards", params={"rarity": "MYTHIC"}).json()
    assert {c["serial"] for c in mythic["items"]} == {3}


def test_sort_newest_oldest_rarest_happiest(make_client: ClientFactory) -> None:
    cards = [
        build_card(1, mint_day=100, rarity="COMMON", happiness=10),
        build_card(2, mint_day=200, rarity="MYTHIC", happiness=90),
        build_card(3, mint_day=300, rarity="RARE", happiness=50),
    ]
    client, _source, _blob = make_client(cards=cards)

    newest = client.get("/api/cards", params={"sort": "newest"}).json()["items"]
    assert [c["serial"] for c in newest] == [3, 2, 1]

    oldest = client.get("/api/cards", params={"sort": "oldest"}).json()["items"]
    assert [c["serial"] for c in oldest] == [1, 2, 3]

    rarest = client.get("/api/cards", params={"sort": "rarest"}).json()["items"]
    assert rarest[0]["serial"] == 2  # MYTHIC ranks first

    happiest = client.get("/api/cards", params={"sort": "happiest"}).json()["items"]
    assert [c["serial"] for c in happiest] == [2, 3, 1]


def test_name_search_is_case_insensitive(make_client: ClientFactory) -> None:
    cards = [
        build_card(1, name="Mochibo"),
        build_card(2, name="Emberling"),
        build_card(3, name="Frostbit"),
    ]
    client, _source, _blob = make_client(cards=cards)
    result = client.get("/api/cards", params={"q": "ember"}).json()
    assert {c["serial"] for c in result["items"]} == {2}


def test_single_card_has_full_shape(client: TestClient) -> None:
    body = client.get("/api/cards/1").json()
    for field in (
        "serial",
        "cardId",
        "name",
        "level",
        "rarity",
        "type",
        "height_mm",
        "weight_g",
        "strength",
        "endurance",
        "agility",
        "happiness",
        "personality",
        "power_name",
        "power_desc",
        "quote",
        "mintDate",
        "imageUrl",
        "thumbUrl",
    ):
        assert field in body, field
    assert body["cardId"] == "PS-0001"
    assert body["imageUrl"] == "/api/cards/1/image"


def test_unknown_serial_is_404_error_shape(client: TestClient) -> None:
    response = client.get("/api/cards/4242")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "card_not_found"


def test_summary_shape_on_listing(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    item = client.get("/api/cards").json()["items"][0]
    assert set(item) == {
        "serial",
        "cardId",
        "name",
        "level",
        "rarity",
        "type",
        "shiny",
        "mintDate",
        "thumbUrl",
        "onChain",
    }


def test_invalid_query_and_path_params_are_422(client: TestClient) -> None:
    assert client.get("/api/cards", params={"size": 101}).status_code == 422
    assert client.get("/api/cards", params={"sort": "loudest"}).status_code == 422
    assert client.get("/api/cards", params={"type": "NOPE"}).status_code == 422
    assert client.get("/api/cards/0").status_code == 422
    assert client.get("/api/cards/70000").status_code == 422
    assert client.get("/api/cards/notanumber").status_code == 422
