"""Tests for the image/thumb proxy routes: caching, conditional GETs and 404s."""

from __future__ import annotations

from _api_helpers import ClientFactory, build_card, load_fixture_card

CACHE_CONTROL = "public, max-age=31536000, immutable"


def test_image_has_immutable_cache_and_etag(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    response = client.get("/api/cards/1/image")
    assert response.status_code == 200
    assert response.headers["cache-control"] == CACHE_CONTROL
    assert response.headers["content-type"] == "image/png"
    assert response.headers.get("etag")


def test_thumb_is_served_as_webp(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    response = client.get("/api/cards/1/thumb")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == CACHE_CONTROL


def test_conditional_get_returns_304(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    first = client.get("/api/cards/1/image")
    etag = first.headers["etag"]

    second = client.get("/api/cards/1/image", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert second.content == b""


def test_wildcard_if_none_match_returns_304(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    response = client.get("/api/cards/1/image", headers={"If-None-Match": "*"})
    assert response.status_code == 304


def test_stale_etag_gets_full_body(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    response = client.get("/api/cards/1/image", headers={"If-None-Match": '"not-the-etag"'})
    assert response.status_code == 200
    assert response.content


def test_image_404_when_card_absent(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    assert client.get("/api/cards/2/image").status_code == 404


def test_image_404_when_blob_missing_but_card_present(make_client: ClientFactory) -> None:
    # Both cards are in the index; drop serial 2's blob to hit the missing-image path.
    client, _source, blob = make_client(
        cards=[load_fixture_card("mochibo"), build_card(2, mint_day=5)]
    )
    del blob._cards[2]
    response = client.get("/api/cards/2/image")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "image_not_found"
