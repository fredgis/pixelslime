"""The anchor job: put a card that already exists in asmDB onto the chain.

W9 built the chain layer and W5 built the jobs, but nothing ever called from one to
the other, so cards were minted into asmDB and never anchored. These tests pin the
seam that closes that gap.

The chain itself is stubbed. What matters here is the *contract between the job and
asmDB* — that a successful mint leaves behind a row which decodes back to the same
transaction, and that a serial already on-chain is not anchored twice.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from _jobs_helpers import FakeAsmDb, build_card

from app.asmdb import AsmDbNotFound
from app.chain import AnchorReceipt, AnchorResult, decode_anchor_row
from app.codec import card_hash, encode
from app.jobs.anchor import AnchorDependencies, anchor_serial

TX_HASH = bytes.fromhex("aa" * 32)
BLOCK = 7_123_456
TOKEN_ID = 1


class StubAnchorer:
    """Stands in for a chain. Records calls and returns a scripted receipt."""

    def __init__(
        self,
        *,
        already_minted: bool = False,
        recovered: AnchorResult | None = None,
    ) -> None:
        self.already_minted = already_minted
        self.recovered = recovered
        self.calls: list[tuple[int, bytes, str]] = []

    def anchor(self, serial: int, card_hash_: bytes, token_uri: str) -> AnchorReceipt:
        self.calls.append((serial, card_hash_, token_uri))
        if self.already_minted:
            return AnchorReceipt(
                serial=serial,
                token_id=serial,
                card_hash=card_hash_,
                already_minted=True,
            )
        return AnchorReceipt(
            serial=serial,
            token_id=TOKEN_ID,
            card_hash=card_hash_,
            already_minted=False,
            tx_hash=TX_HASH,
            block_number=BLOCK,
        )

    def find_mint(self, serial: int) -> AnchorResult | None:
        del serial
        return self.recovered


class StubBloomRecorder:
    """Stands in for ClaimPool.recordBloom, including its refusal to repeat.

    The real pool now rejects a second bloom for the same serial, so this stub does
    too. Modelling that here matters: the job deliberately re-attempts a bloom it
    cannot prove succeeded, and it is the pool — not the caller — that must be the
    thing which makes a double burn impossible.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, str, int]] = []
        self.recorded: set[int] = set()

    def record_bloom(self, serial: int, rarity: str, happiness: int) -> bytes | None:
        if self.fail:
            raise RuntimeError("pool unreachable")
        if serial in self.recorded:
            return None
        self.calls.append((serial, rarity, happiness))
        self.recorded.add(serial)
        return b"\xbb" * 32


class FakeRepository:
    """The slice of the W3 repository the anchor job touches.

    Mirrors the real repository in one easily-missed way: ``read_card_rows`` returns
    the card's own contiguous parts and **not** the part 8 anchor row. An earlier
    version of this fake returned everything, which let a bug through — the job
    believed it could detect an existing anchor from this call alone, and in
    production it therefore re-scanned chain logs on every single run.
    """

    def __init__(self, db: FakeAsmDb) -> None:
        self._db = db

    async def read_card_rows(self, serial: int) -> list[object]:
        prefix = f"psc.{serial}."
        return [
            row
            for row in self._db.rows.values()
            if str(row.tag).startswith(prefix) and row.id % 16 != 8
        ]


class FakeRowWriter:
    """Reads and writes one addressed row, the way asmDB's get/upsert do."""

    def __init__(self, db: FakeAsmDb) -> None:
        self._db = db
        self.written: list[object] = []

    async def get(self, row_id: int) -> object:
        row = self._db.rows.get(row_id)
        if row is None:
            raise AsmDbNotFound("missing row", code="not_found", status_code=404)
        return row

    async def upsert(self, row: object) -> object:
        self._db.rows[row.id] = row  # type: ignore[attr-defined]
        self.written.append(row)
        return row


def _seeded(serial: int = 1) -> tuple[AnchorDependencies, FakeAsmDb, object]:
    db = FakeAsmDb(events=[])
    card = build_card(serial=serial, mint_day=1)
    db.seed(card)
    return (
        AnchorDependencies(
            repository=FakeRepository(db),
            writer=FakeRowWriter(db),
            anchorer=StubAnchorer(),
        ),
        db,
        card,
    )


@pytest.mark.asyncio
async def test_anchoring_writes_a_row_that_decodes_to_the_transaction() -> None:
    deps, db, card = _seeded()

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is True
    # The hash handed to the chain must be the keccak of the canonical stream,
    # not of anything the job re-derived on its own.
    assert deps.anchorer.calls[0][1] == card_hash(card)  # type: ignore[attr-defined]

    stored = db.rows[1 * 16 + 8]
    decoded = decode_anchor_row(stored.content, expected_serial=1)
    assert decoded.tx_hash == TX_HASH
    assert decoded.block_number == BLOCK
    assert decoded.card_hash == card_hash(card)
    assert decoded.explorer_url is not None


@pytest.mark.asyncio
async def test_a_serial_already_on_chain_is_not_anchored_twice() -> None:
    deps, db, _ = _seeded()
    deps = replace(deps, anchorer=StubAnchorer(already_minted=True))

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is False
    assert (1 * 16 + 8) not in db.rows


@pytest.mark.asyncio
async def test_an_unknown_serial_is_reported_rather_than_anchored() -> None:
    db = FakeAsmDb(events=[])
    anchorer = StubAnchorer()
    deps = AnchorDependencies(
        repository=FakeRepository(db),
        writer=FakeRowWriter(db),
        anchorer=anchorer,
    )

    with pytest.raises(LookupError):
        await anchor_serial(99, deps=deps)

    assert anchorer.calls == []


@pytest.mark.asyncio
async def test_the_token_uri_addresses_the_serial() -> None:
    deps, _, _ = _seeded()
    deps = replace(deps, token_uri_base="https://pixelslime.cloud/api/cards/")

    await anchor_serial(1, deps=deps)

    assert deps.anchorer.calls[0][2] == "https://pixelslime.cloud/api/cards/1"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_second_run_after_success_does_not_re_anchor() -> None:
    # The row written by the first run is what makes a re-run cheap: the job must
    # notice it and return before it ever asks the chain anything.
    deps, _, _ = _seeded()
    await anchor_serial(1, deps=deps)
    calls_after_first = len(deps.anchorer.calls)  # type: ignore[attr-defined]

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is False
    assert len(deps.anchorer.calls) == calls_after_first  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_mint_that_landed_without_its_row_is_recovered() -> None:
    # The dangerous window: the mint transaction is confirmed on-chain but the
    # process dies before asmDB is written. The chain then reports "already minted"
    # forever, so without recovery the card could never be anchored in the database
    # and the site would show ANCHOR PENDING for a card that is demonstrably on the
    # chain. The job must heal that by asking the chain for the original mint.
    deps, db, card = _seeded()
    recovered = AnchorResult(
        serial=1,
        tx_hash=TX_HASH,
        block_number=BLOCK,
        token_id=TOKEN_ID,
        card_hash=card_hash(card),
    )
    deps = replace(
        deps,
        anchorer=StubAnchorer(already_minted=True, recovered=recovered),
    )

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is True
    decoded = decode_anchor_row(db.rows[1 * 16 + 8].content, expected_serial=1)
    assert decoded.tx_hash == TX_HASH
    assert decoded.card_hash == card_hash(card)


@pytest.mark.asyncio
async def test_recovery_is_skipped_when_the_chain_cannot_find_the_mint() -> None:
    deps, db, _ = _seeded()
    deps = replace(deps, anchorer=StubAnchorer(already_minted=True, recovered=None))

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is False
    assert (1 * 16 + 8) not in db.rows


@pytest.mark.asyncio
async def test_a_successful_anchor_records_the_bloom() -> None:
    # Anchoring mints the SLIME card; recording the bloom is what moves SMILE — it
    # burns the fee out of the finite Genesis Rain and mints the yield into the pool.
    # Without this the economy never starts, and a skipped day can never be recovered
    # because the reserve drains on a fixed 3,650-bloom schedule.
    deps, _, card = _seeded()
    recorder = StubBloomRecorder()
    deps = replace(deps, bloom=recorder)

    await anchor_serial(1, deps=deps)

    assert recorder.calls == [(1, card.rarity, card.happiness)]


@pytest.mark.asyncio
async def test_the_bloom_is_not_recorded_twice_for_the_same_card() -> None:
    # The job re-attempts a bloom it cannot prove succeeded, so the pool is what makes
    # a double burn impossible. This pins that the *effect* happens once, not that the
    # call happens once — the weaker of those two was all the client could ever offer.
    deps, _, _ = _seeded()
    recorder = StubBloomRecorder()
    deps = replace(deps, bloom=recorder)

    await anchor_serial(1, deps=deps)
    await anchor_serial(1, deps=deps)

    assert len(recorder.calls) == 1
    assert recorder.recorded == {1}


@pytest.mark.asyncio
async def test_a_bloom_failure_does_not_lose_the_anchor() -> None:
    # The anchor row is the record that the card is on-chain. If recording the bloom
    # fails — an RPC blip, an exhausted reserve — that row must still be written, or
    # the next run would try to mint a card the chain already has.
    deps, db, _ = _seeded()
    deps = replace(deps, bloom=StubBloomRecorder(fail=True))

    outcome = await anchor_serial(1, deps=deps)

    assert outcome.anchored is True
    assert (1 * 16 + 8) in db.rows


@pytest.mark.asyncio
async def test_a_failed_bloom_is_retried_on_the_next_run() -> None:
    # The anchor row short-circuits the mint, which is correct — minting is not
    # repeatable. But the bloom is a separate, retryable act, and returning early on
    # the row meant a swallowed bloom failure could never be recovered: the fee would
    # never be burned for that card, leaving the ten-year schedule permanently short
    # with nothing to signal it.
    deps, _, card = _seeded()
    failing = StubBloomRecorder(fail=True)
    await anchor_serial(1, deps=replace(deps, bloom=failing))

    recovering = StubBloomRecorder()
    outcome = await anchor_serial(1, deps=replace(deps, bloom=recovering))

    assert outcome.anchored is False  # the card was already on-chain
    assert recovering.calls == [(1, card.rarity, card.happiness)]


@pytest.mark.asyncio
async def test_a_serial_bloomed_against_a_retired_pool_is_not_bloomed_again() -> None:
    # Replacing the ClaimPool resets every bloomRecorded flag, because the new pool has
    # never seen any of them. A catch-up sweep would then walk the whole collection and
    # re-burn the fee for cards that already paid it into the retired pool — the exact
    # double-burn the replacement existed to prevent. The floor states where the new
    # pool's history begins, so the two generations cannot overlap.
    deps, _, _ = _seeded()
    recorder = StubBloomRecorder()
    deps = replace(deps, bloom=recorder, bloom_min_serial=2)

    await anchor_serial(1, deps=deps)

    assert recorder.calls == []


@pytest.mark.asyncio
async def test_the_floor_does_not_block_later_serials() -> None:
    db = FakeAsmDb(events=[])
    card = build_card(serial=5, mint_day=5)
    db.seed(card)
    recorder = StubBloomRecorder()
    deps = AnchorDependencies(
        repository=FakeRepository(db),
        writer=FakeRowWriter(db),
        anchorer=StubAnchorer(),
        bloom=recorder,
        bloom_min_serial=2,
    )

    await anchor_serial(5, deps=deps)

    assert recorder.calls == [(5, card.rarity, card.happiness)]


def test_encode_is_importable() -> None:
    # Guards against the helper drifting away from the codec surface the job uses.
    assert callable(encode)
