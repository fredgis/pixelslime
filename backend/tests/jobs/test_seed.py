"""Collection seeding reuses the viable W4 exemplar without compromising IDs."""

from __future__ import annotations

from pathlib import Path

import pytest
from _jobs_helpers import build_card, fake_environment

from app.jobs._operations import read_card
from app.jobs.errors import JobError
from app.jobs.seed import run_seed

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = Path(__file__).resolve().parents[2]
_MOCHIBO_PNG = _REPO_ROOT / "assets" / "template" / "mochibo.png"
_LEGENDARY_PNG = _BACKEND / "tests" / "ai" / "output" / "legendary.png"


async def test_seed_imports_mochibo_reuses_legendary_and_generates_common_rare() -> None:
    env = fake_environment()

    result = await run_seed(env.deps)

    cards = {serial: await read_card(env.deps, serial) for serial in range(1, 5)}
    assert cards[1].name == "Mochibo"
    assert cards[1].rarity == "EPIC"
    assert cards[2].name == "Thundersnuggle"
    assert cards[2].rarity == "LEGENDARY"
    assert cards[3].rarity == "COMMON"
    assert cards[4].rarity == "RARE"
    assert all(card.flags.seed for card in cards.values())
    assert [call["forced_rarity"] for call in env.generator.calls] == ["COMMON", "RARE"]
    assert [call["serial"] for call in env.generator.calls] == [3, 4]
    assert result.created == (1, 2, 3, 4)
    assert result.reused_w4 == ("LEGENDARY",)
    assert env.blob.cards[1] == _MOCHIBO_PNG.read_bytes()
    assert env.blob.cards[2] == _LEGENDARY_PNG.read_bytes()


async def test_seed_is_idempotent_on_fixed_serials_and_dates() -> None:
    env = fake_environment()

    await run_seed(env.deps)
    env.generator.calls.clear()
    second = await run_seed(env.deps)

    assert second.created == ()
    assert second.skipped == (1, 2, 3, 4)
    assert env.generator.calls == []


async def test_seed_rejects_a_conflicting_fixed_serial() -> None:
    env = fake_environment()
    env.asmdb.seed(build_card(1, 10, rarity="COMMON", name="Imposter", seed=True))

    with pytest.raises(JobError, match="PS-0001"):
        await run_seed(env.deps)

    assert env.generator.calls == []
