"""Provenance (`/raw`) shape and a real round-trip through the codec + fake asmDB."""

from __future__ import annotations

from _api_helpers import ClientFactory, load_fixture_card

from app.codec import card_hash, encode, encode_stream


def test_raw_shape_matches_contract(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    body = client.get("/api/cards/1/raw").json()

    assert set(body) == {"rows", "streamBytes", "rowCount", "cardHash", "decoded"}
    assert body["rowCount"] == len(body["rows"])
    assert body["cardHash"].startswith("0x")
    assert len(body["cardHash"]) == 66  # 0x + 64 hex chars
    for row in body["rows"]:
        assert set(row) == {"id", "value", "tag", "content"}
        assert isinstance(row["id"], str)
        assert isinstance(row["value"], str)


def test_raw_is_byte_identical_to_the_codec(make_client: ClientFactory) -> None:
    """Encode mochibo independently and assert the API returns exactly those rows."""
    card = load_fixture_card("mochibo")
    client, _source, _blob = make_client(cards=[card])

    expected_rows = encode(card)
    expected = {
        "rows": [
            {"id": str(r.id), "value": str(r.value), "tag": r.tag, "content": r.content}
            for r in expected_rows
        ],
        "streamBytes": len(encode_stream(card)),
        "rowCount": len(expected_rows),
        "cardHash": "0x" + card_hash(card).hex(),
    }

    body = client.get("/api/cards/1/raw").json()
    assert body["rows"] == expected["rows"]
    assert body["streamBytes"] == expected["streamBytes"]
    assert body["rowCount"] == expected["rowCount"]
    assert body["cardHash"] == expected["cardHash"]


def test_raw_decoded_matches_single_card(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    decoded = client.get("/api/cards/1/raw").json()["decoded"]
    detail = client.get("/api/cards/1").json()
    assert decoded == detail


def test_raw_unknown_serial_is_404(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[load_fixture_card("mochibo")])
    response = client.get("/api/cards/999/raw")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "card_not_found"
