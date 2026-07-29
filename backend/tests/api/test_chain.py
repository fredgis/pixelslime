"""D2 — the on-chain anchor (PSC-1 part 8) drives ``chain`` and ``onChain``.

The rule W10 found broken: ``chain`` and the ``onChain`` badge must come from the
*anchor row* — the evidence in asmDB — and never from the header ``flags.on_chain``
bit, which a crash between mint and anchor-write can leave set with no row. And the
gallery summary and the card detail must never disagree about whether a card is
anchored, because both now read the one decoded anchor the index holds.
"""

from __future__ import annotations

import json

from _api_helpers import ClientFactory, anchor_for, build_card, card_minted_today

from app.chain import build_anchor_row_from_result
from app.core.chain import decode_anchor_content
from app.core.index import CardIndex


def test_anchored_card_populates_chain_detail(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(
        cards=[build_card(7)],
        anchors=[anchor_for(7, token_id=123, block_number=456789, tx_byte=0xAB)],
    )
    body = client.get("/api/cards/7").json()
    assert body["onChain"] is True
    assert body["chain"] == {
        "tokenId": 123,
        "txHash": "0x" + "ab" * 8,  # only the 8-byte prefix is stored on-chain (§4.4)
        "blockNumber": 456789,
    }


def test_summary_and_detail_never_disagree_about_anchored(make_client: ClientFactory) -> None:
    # A deliberately mixed collection: one truly anchored (row present), one plain,
    # and one with flags.on_chain set but *no* anchor row (the seed-65535 trap).
    cards = [build_card(1), build_card(2), build_card(3, on_chain=True)]
    client, _source, _blob = make_client(cards=cards, anchors=[anchor_for(1)])

    detail = {c: client.get(f"/api/cards/{c}").json() for c in (1, 2, 3)}
    summary = {item["serial"]: item for item in client.get("/api/cards").json()["items"]}

    # The invariant D2 is really about: for every card, three views give one answer.
    for serial in (1, 2, 3):
        d, s = detail[serial], summary[serial]
        assert s["onChain"] == d["onChain"] == (d["chain"] is not None), serial

    assert detail[1]["onChain"] is True  # row present → anchored
    assert detail[2]["onChain"] is False  # nothing → not anchored
    assert detail[3]["onChain"] is False  # flag set but no row → NOT anchored
    assert detail[3]["chain"] is None


def test_flag_without_row_is_not_trusted(make_client: ClientFactory) -> None:
    # Reproduces seed serial 65535: flags.on_chain=true, but no anchor row was written.
    client, _source, _blob = make_client(cards=[build_card(65535, on_chain=True)])
    detail = client.get("/api/cards/65535").json()
    summary = client.get("/api/cards").json()["items"][0]
    assert detail["onChain"] is False
    assert detail["chain"] is None
    assert summary["onChain"] is False


def test_raw_view_decoded_reflects_chain(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(cards=[build_card(9)], anchors=[anchor_for(9)])
    raw = client.get("/api/cards/9/raw").json()
    detail = client.get("/api/cards/9").json()
    assert raw["decoded"]["onChain"] is True
    assert raw["decoded"]["chain"] == detail["chain"]


def test_today_card_surfaces_chain(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(
        cards=[card_minted_today(serial=5)],
        anchors=[anchor_for(5, token_id=5)],
    )
    card = client.get("/api/cards/today").json()["card"]
    assert card["onChain"] is True
    assert card["chain"]["tokenId"] == 5


# ── the decoder itself (app/chain/ ships no decoder; core owns it) ────────────
def test_decode_anchor_round_trips_the_real_encoder() -> None:
    row = build_anchor_row_from_result(anchor_for(42, token_id=7, block_number=99, tx_byte=0x11))
    anchor = decode_anchor_content(row.content, serial=42)
    assert anchor is not None
    assert anchor.token_id == 7
    assert anchor.block_number == 99
    assert anchor.tx_hash == "0x" + "11" * 8


def test_decode_anchor_rejects_bad_content() -> None:
    assert decode_anchor_content("not valid z85 at all", serial=1) is None
    assert decode_anchor_content("", serial=1) is None


def test_decode_anchor_rejects_serial_mismatch() -> None:
    row = build_anchor_row_from_result(anchor_for(42))
    assert decode_anchor_content(row.content, serial=99) is None  # row is for 42, not 99


# ── warm-start persistence: a restart must not lose a card's anchor ───────────
def test_index_persistence_preserves_chain() -> None:
    row = build_anchor_row_from_result(anchor_for(3, token_id=8, block_number=77, tx_byte=0x22))
    anchor = decode_anchor_content(row.content, serial=3)
    assert anchor is not None

    index = CardIndex()
    index.upsert(build_card(3), anchor)
    index.upsert(build_card(4))  # unanchored

    restored = CardIndex()
    restored.load_json_bytes(index.to_json_bytes())

    reloaded = restored.chain_for(3)
    assert reloaded is not None
    assert reloaded.token_id == 8
    assert reloaded.block_number == 77
    assert reloaded.tx_hash == anchor.tx_hash
    assert restored.chain_for(4) is None


def test_index_persistence_reads_legacy_flat_cards() -> None:
    # Older index.json entries were flat card dumps with no chain wrapper — still load.
    legacy = json.dumps({"version": 1, "cards": [build_card(11).model_dump(mode="json")]}).encode(
        "utf-8"
    )
    index = CardIndex()
    index.load_json_bytes(legacy)
    assert index.contains(11)
    assert index.chain_for(11) is None
