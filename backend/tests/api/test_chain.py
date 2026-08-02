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
from app.chain.anchor_row import AMOY_EXPLORER_TX_BASE
from app.core.chain import read_anchor
from app.core.index import CardIndex
from app.core.source import InMemoryCardSource


def test_anchored_card_populates_chain_detail(make_client: ClientFactory) -> None:
    client, _source, _blob = make_client(
        cards=[build_card(7)],
        anchors=[anchor_for(7, token_id=123, block_number=456789, tx_byte=0xAB)],
    )
    body = client.get("/api/cards/7").json()
    assert body["onChain"] is True
    assert body["chain"] == {
        "tokenId": 123,
        "txHash": "0x" + "ab" * 32,  # v0x02 stores the full 32-byte transaction hash (§4.4)
        "blockNumber": 456789,
        "explorerUrl": AMOY_EXPLORER_TX_BASE + "0x" + "ab" * 32,
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


# ── the read-path decoder wrapper (app/chain/ owns the codec; core degrades it) ──
def test_decode_anchor_round_trips_the_real_encoder() -> None:
    row = build_anchor_row_from_result(anchor_for(42, token_id=7, block_number=99, tx_byte=0x11))
    anchor = read_anchor(row.content, serial=42)
    assert anchor is not None
    assert anchor.token_id == 7
    assert anchor.block_number == 99
    assert anchor.tx_hash_hex == "0x" + "11" * 32


def test_decode_anchor_rejects_bad_content() -> None:
    assert read_anchor("not valid z85 at all", serial=1) is None
    assert read_anchor("", serial=1) is None


def test_decode_anchor_rejects_serial_mismatch() -> None:
    row = build_anchor_row_from_result(anchor_for(42))
    assert read_anchor(row.content, serial=99) is None  # row is for 42, not 99


# ── warm-start persistence: a restart must not lose a card's anchor ───────────
def test_index_persistence_preserves_chain() -> None:
    row = build_anchor_row_from_result(anchor_for(3, token_id=8, block_number=77, tx_byte=0x22))
    anchor = read_anchor(row.content, serial=3)
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


# ── targeted refresh: a late async anchor must surface without a restart ───────
async def test_refresh_chain_folds_in_a_late_anchor() -> None:
    # Minting and anchoring are decoupled (PLAN §8.13): the card is indexed first, its
    # part=8 row lands days later, and the add-only reconcile never revisits it.
    source = InMemoryCardSource()
    source.add_card(build_card(12, on_chain=True))  # header claims on-chain...
    index = CardIndex()
    await index.reconcile(source)
    assert index.chain_for(12) is None  # ...but the anchor row has not landed yet

    source.add_anchor(anchor_for(12, token_id=77))  # the asynchronous anchor arrives
    assert await index.refresh_chain(source, 12) is True

    anchor = index.chain_for(12)
    assert anchor is not None
    assert anchor.token_id == 77


async def test_refresh_pending_anchors_only_polls_flagged_cards() -> None:
    source = InMemoryCardSource()
    source.add_card(build_card(1, on_chain=True))  # mid-anchor: flag set, row pending
    source.add_card(build_card(2))  # flag clear: never expected on-chain
    index = CardIndex()
    await index.reconcile(source)

    # Nothing to surface until a row exists.
    assert await index.refresh_pending_anchors(source) == 0

    source.add_anchor(anchor_for(1))  # card 1's row lands
    source.add_anchor(anchor_for(2))  # card 2 gets one out of band too
    assert await index.refresh_pending_anchors(source) == 1  # only the flagged card is re-read

    assert index.chain_for(1) is not None
    assert index.chain_for(2) is None  # flag clear → never polled, so never a wasted read


async def test_startup_sweep_surfaces_anchors_the_flag_never_predicted() -> None:
    # refresh_pending_anchors deliberately trusts flags.on_chain to bound its work,
    # which assumes anchoring always follows minting inside one lifecycle. That breaks
    # the moment a chain is introduced to a collection that already exists: those cards
    # were encoded with the flag clear, and the flag cannot be flipped afterwards
    # because it is part of the hashed stream — rewriting it would invalidate the very
    # cardHash already committed on-chain. The startup sweep is the escape: it costs
    # one pass over the unanchored cards, and it drains as they are anchored.
    source = InMemoryCardSource()
    source.add_card(build_card(1))  # flag clear, anchored retroactively
    index = CardIndex()
    await index.reconcile(source)
    assert index.chain_for(1) is None

    source.add_anchor(anchor_for(1))

    assert await index.refresh_unanchored(source) == 1
    assert index.chain_for(1) is not None


async def test_startup_sweep_is_capped_so_a_large_unanchored_tail_cannot_stall_boot() -> None:
    source = InMemoryCardSource()
    for serial in range(1, 6):
        source.add_card(build_card(serial))
    index = CardIndex()
    await index.reconcile(source)
    for serial in range(1, 6):
        source.add_anchor(anchor_for(serial))

    assert await index.refresh_unanchored(source, limit=2) == 2


async def test_a_card_anchored_after_boot_is_surfaced_without_a_restart() -> None:
    # The real sequence, and the one that broke production: a long-running replica
    # picks up tomorrow's card through the periodic reconcile, the anchor job writes
    # its part-8 row half an hour later, and nothing ever re-reads it. The card then
    # shows ANCHOR PENDING until someone happens to restart the app -- which is how
    # PS-0005 and PS-0006 sat pending for days while provably on-chain.
    #
    # refresh_pending_anchors cannot close this: it polls only cards whose header
    # flags.on_chain is set, and that bit is written at creation, before any anchor
    # exists. It is false on every card ever minted, so that sweep polls nothing.
    source = InMemoryCardSource()
    index = CardIndex()
    await index.reconcile(source)

    # A new card blooms after boot and is folded in with no anchor yet.
    source.add_card(build_card(7))
    await index.reconcile(source)
    assert index.chain_for(7) is None

    # The anchor job lands its row later.
    source.add_anchor(anchor_for(7))

    # The flag-bounded sweep is blind to it, by design.
    assert await index.refresh_pending_anchors(source) == 0
    assert index.chain_for(7) is None

    # The evidence-based sweep is what the periodic loop must call.
    assert await index.refresh_unanchored(source) == 1
    assert index.chain_for(7) is not None


async def test_the_periodic_loop_surfaces_an_anchor_written_after_boot() -> None:
    # The test above pins the index methods; this one pins the *caller*, which is where
    # the defect actually lived. bootstrap_index swept correctly while _reconcile_loop
    # kept calling the flag-bounded version, so a card anchored after boot stayed
    # pending until a restart. Nothing tested the loop, which is why it went unnoticed.
    import asyncio

    from app.core.config import Settings
    from app.main import _reconcile_loop
    from app.storage.blob import InMemoryBlobStore

    source = InMemoryCardSource()
    source.add_card(build_card(9))
    index = CardIndex()
    await index.reconcile(source)
    assert index.chain_for(9) is None

    source.add_anchor(anchor_for(9))

    settings = Settings(INDEX_REFRESH_SECONDS=0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(_reconcile_loop(settings, source, InMemoryBlobStore(), index, stop))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if index.chain_for(9) is not None:
            break
    stop.set()
    await task

    assert index.chain_for(9) is not None, "the periodic loop never re-read the anchor"
