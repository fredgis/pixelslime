"""The sweep must not report success when it anchored nothing.

PS-0012 sat on ANCHOR PENDING for a day while the scheduled job reported *Succeeded*
twice. Nothing was broken in the anchoring logic: the gas wallet had run dry, 0.0002 POL
short of a single transaction. The failure was that ``_run`` caught every exception per
serial and then returned normally, so a total outage and a healthy run produced an
identical execution history — and the only remaining signal was a visitor noticing a
card stuck on the site.

Tolerating one awkward serial is deliberate and stays. Claiming success after failing
every serial is what these tests forbid.
"""

from __future__ import annotations

from typing import Any

import pytest
from _jobs_helpers import FakeAsmDb, build_card

from app.chain import AnchorReceipt
from app.jobs import anchor as anchor_module
from app.jobs.errors import JobError


class _ExplodingAnchorer:
    """A chain that rejects every transaction, the way an empty wallet does."""

    def __init__(self, *, fail_serials: set[int], balance_wei: int = 0) -> None:
        self.fail_serials = fail_serials
        self.gas_balance_wei = balance_wei
        self.attempted: list[int] = []

    def anchor(self, serial: int, card_hash_: bytes, token_uri: str) -> AnchorReceipt:
        del token_uri
        self.attempted.append(serial)
        if serial in self.fail_serials:
            raise RuntimeError(
                "insufficient funds for gas * price + value: balance 7285515872756609, "
                "tx cost 7500000031500000"
            )
        return AnchorReceipt(
            serial=serial,
            token_id=serial,
            card_hash=card_hash_,
            already_minted=False,
            tx_hash=bytes.fromhex("aa" * 32),
            block_number=1,
        )

    def find_mint(self, serial: int) -> None:
        del serial
        return None


def _install(
    monkeypatch: pytest.MonkeyPatch, anchorer: _ExplodingAnchorer, serials: list[int]
) -> FakeAsmDb:
    """Point ``_run`` at fakes while leaving its own control flow untouched.

    The whole value of these tests is that they drive the real ``_run``: the bug lived
    in its loop, not in ``anchor_serial``, so a test that called the latter would have
    passed throughout the incident.
    """
    db = FakeAsmDb(events=[])
    for serial in serials:
        db.seed(build_card(serial=serial, mint_day=serial))

    class _Repo:
        async def read_card_rows(self, serial: int) -> list[object]:
            prefix = f"psc.{serial}."
            return [r for r in db.rows.values() if str(r.tag).startswith(prefix) and r.id % 16 != 8]

        async def list_card_serials(self) -> list[int]:
            return list(serials)

    class _Writer:
        async def get(self, row_id: int) -> object:
            from app.asmdb import AsmDbNotFound

            row = db.rows.get(row_id)
            if row is None:
                raise AsmDbNotFound("missing row", code="not_found", status_code=404)
            return row

        async def upsert(self, row: Any) -> object:
            db.rows[row.id] = row
            return row

        async def aclose(self) -> None:
            return None

    class _Settings:
        asmdb_url = "https://asmdb.example/db/x"
        log_level = "INFO"

    class _Secrets:
        def asmdb_bearer_for_client(self) -> str:
            return "token"

    async def _load_secrets(_settings: object) -> _Secrets:
        return _Secrets()

    monkeypatch.setattr("app.core.config.load_settings", lambda: _Settings())
    monkeypatch.setattr("app.core.logging.configure_logging", lambda _level: None)
    monkeypatch.setattr("app.core.secrets.load_secrets", _load_secrets)
    monkeypatch.setattr("app.asmdb.AsmDbClient", lambda *a, **k: _Writer())
    monkeypatch.setattr("app.asmdb.AsmDbRepository", lambda _client: _Repo())

    class _ChainSettings:
        bloom_min_serial = 2

    monkeypatch.setattr(anchor_module, "load_chain_settings", lambda: _ChainSettings())
    monkeypatch.setattr(anchor_module, "_build_anchorer", lambda _s: anchorer)
    monkeypatch.setattr(anchor_module, "_build_bloom_recorder", lambda _s, _a: None)
    return db


@pytest.mark.asyncio
async def test_a_sweep_that_anchors_nothing_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact PS-0012 shape: every serial rejected, and the job used to say Succeeded."""
    anchorer = _ExplodingAnchorer(fail_serials={1, 2, 3})
    _install(monkeypatch, anchorer, [1, 2, 3])

    with pytest.raises(JobError) as excinfo:
        await anchor_module._run([])

    # Every serial was still attempted - failing fast would trade one bug for another.
    assert anchorer.attempted == [1, 2, 3]
    assert "3 of 3" in str(excinfo.value)


@pytest.mark.asyncio
async def test_one_bad_serial_still_lets_the_others_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tolerance that motivated the original ``continue`` is preserved.

    A catch-up run exists to make progress through a backlog, so a single unanchorable
    serial must not abandon the rest. It must, however, still be reported.
    """
    anchorer = _ExplodingAnchorer(fail_serials={2})
    _install(monkeypatch, anchorer, [1, 2, 3])

    with pytest.raises(JobError) as excinfo:
        await anchor_module._run([])

    assert anchorer.attempted == [1, 2, 3]
    assert "1 of 3" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_clean_sweep_still_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    anchorer = _ExplodingAnchorer(fail_serials=set(), balance_wei=10**18)
    _install(monkeypatch, anchorer, [1, 2])

    await anchor_module._run([])

    assert anchorer.attempted == [1, 2]


def test_low_gas_is_warned_about_before_it_bites() -> None:
    """The balance is reported every run, and flagged while there is still runway.

    An empty wallet is not a bug to fix in code - it is a supply to top up, and the
    only thing that makes it an incident is finding out too late.
    """
    logged: list[tuple[str, dict[str, Any]]] = []

    class _Log:
        def info(self, event: str, **kw: Any) -> None:
            logged.append((event, kw))

        def warning(self, event: str, **kw: Any) -> None:
            logged.append((event, kw))

    original = anchor_module._log
    anchor_module._log = _Log()  # type: ignore[assignment]
    try:
        # 0.0075 POL per anchor: this is a hair under two runs' worth.
        anchor_module._log_gas_balance(_ExplodingAnchorer(fail_serials=set(), balance_wei=10**16))
        assert logged[-1][0] == "gas_balance_low"
        assert logged[-1][1]["anchors_left"] == 1

        logged.clear()
        anchor_module._log_gas_balance(_ExplodingAnchorer(fail_serials=set(), balance_wei=10**18))
        assert logged[-1][0] == "gas_balance"
        assert logged[-1][1]["anchors_left"] > 100
    finally:
        anchor_module._log = original  # type: ignore[assignment]
