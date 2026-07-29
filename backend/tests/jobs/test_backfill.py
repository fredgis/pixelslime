"""Catch-up generation is inclusive, idempotent and deliberately paced."""

from __future__ import annotations

from datetime import date

import pytest
from _jobs_helpers import build_card, fake_environment

from app.jobs._operations import mint_day_for_date
from app.jobs.backfill import run_backfill


async def test_backfill_creates_every_missing_day_with_sequential_serials() -> None:
    env = fake_environment()

    result = await run_backfill(
        env.deps,
        start=date(2026, 7, 20),
        end=date(2026, 7, 22),
    )

    assert result.created == (
        (date(2026, 7, 20), 1),
        (date(2026, 7, 21), 2),
        (date(2026, 7, 22), 3),
    )
    assert result.skipped == ()
    assert [call["mint_day"] for call in env.generator.calls] == [
        mint_day_for_date(date(2026, 7, 20)),
        mint_day_for_date(date(2026, 7, 21)),
        mint_day_for_date(date(2026, 7, 22)),
    ]
    assert [call["serial"] for call in env.generator.calls] == [1, 2, 3]
    assert env.clock.sleeps == [35.0, 35.0]


async def test_backfill_skips_existing_dates_and_paces_only_real_generations() -> None:
    env = fake_environment()
    existing_day = date(2026, 7, 21)
    env.asmdb.seed(build_card(5, mint_day_for_date(existing_day)))

    result = await run_backfill(
        env.deps,
        start=date(2026, 7, 20),
        end=date(2026, 7, 22),
    )

    assert result.created == ((date(2026, 7, 20), 6), (date(2026, 7, 22), 7))
    assert result.skipped == ((existing_day, 5),)
    assert env.clock.sleeps == [35.0]


async def test_backfill_rerun_is_idempotent_per_date() -> None:
    env = fake_environment()
    start = date(2026, 7, 20)
    end = date(2026, 7, 22)

    first = await run_backfill(env.deps, start=start, end=end)
    env.generator.calls.clear()
    env.clock.sleeps.clear()
    second = await run_backfill(env.deps, start=start, end=end)

    assert len(first.created) == 3
    assert second.created == ()
    assert len(second.skipped) == 3
    assert env.generator.calls == []
    assert env.clock.sleeps == []


async def test_backfill_rejects_an_inverted_range_before_warming_asmdb() -> None:
    env = fake_environment()

    with pytest.raises(ValueError, match="start date"):
        await run_backfill(
            env.deps,
            start=date(2026, 7, 22),
            end=date(2026, 7, 20),
        )

    assert env.events == []
