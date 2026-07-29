"""Daily-job behavior at its public orchestration seam."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from _jobs_helpers import build_card, fake_environment
from structlog.testing import capture_logs

from app.ai import (
    ImageGenerationError,
    MetadataError,
    PostProcessError,
    RollError,
    VerificationError,
)
from app.asmdb import AsmDbError
from app.jobs._operations import mint_day_for_date
from app.jobs.daily import run_daily, run_scheduled
from app.jobs.errors import GenerationJobError, RollbackError, RoundTripError


@pytest.mark.parametrize(
    ("now_utc", "expected"),
    [
        (datetime(2026, 3, 29, 8, tzinfo=UTC), "created"),
        (datetime(2026, 3, 29, 9, tzinfo=UTC), "stood_down"),
        (datetime(2026, 3, 29, 10, tzinfo=UTC), "stood_down"),
        (datetime(2026, 10, 25, 8, tzinfo=UTC), "stood_down"),
        (datetime(2026, 10, 25, 9, tzinfo=UTC), "created"),
        (datetime(2026, 10, 25, 10, tzinfo=UTC), "stood_down"),
    ],
)
async def test_paris_guard_across_both_dst_transitions(
    now_utc: datetime,
    expected: str,
) -> None:
    env = fake_environment()

    result = await run_daily(env.deps, now_utc=now_utc)

    assert result.status == expected
    if expected == "stood_down":
        assert env.events == []
    else:
        assert env.events[0] == "asmdb.warm"


async def test_scheduled_entrypoint_guards_before_production_wiring() -> None:
    result = await run_scheduled(
        now_utc=datetime(2026, 3, 29, 9, tzinfo=UTC),
    )

    assert result.status == "stood_down"


async def test_existing_mint_date_exits_before_serial_or_generation() -> None:
    env = fake_environment()
    mint_date = date(2026, 7, 29)
    env.asmdb.seed(build_card(9, mint_day_for_date(mint_date)))

    result = await run_daily(
        env.deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )

    assert result.status == "already_exists"
    assert result.serial == 9
    assert env.events == ["asmdb.warm", "rows.find:20260729"]


async def test_serial_is_max_existing_plus_one_and_history_is_forwarded() -> None:
    env = fake_environment()
    env.asmdb.seed(build_card(2, 100, rarity="COMMON", name="Older"))
    env.asmdb.seed(build_card(7, 101, rarity="RARE", name="Newest"))

    result = await run_daily(
        env.deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )

    assert result.serial == 8
    call = env.generator.calls[0]
    assert call["serial"] == 8
    assert [item.rarity for item in call["history"]] == ["COMMON", "RARE"]  # type: ignore[union-attr]
    assert call["used_names"] == ("Older", "Newest")


async def test_persistence_is_blob_then_rows_then_semantic_readback_then_index() -> None:
    env = fake_environment()

    await run_daily(
        env.deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )

    assert env.events.index("blob.put:1") < env.events.index("rows.write")
    assert env.events.index("rows.write") < env.events.index("rows.read:1")
    assert env.events.index("rows.read:1") < env.events.index("blob.index")


async def test_corrupt_semantic_readback_rolls_back_rows_but_keeps_orphan_blob() -> None:
    env = fake_environment()
    env.asmdb.corrupt_read_back = True

    with pytest.raises(RoundTripError, match="diverged"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.asmdb.rows == {}
    assert env.blob.cards[1] == b"png-1"
    assert any(event.startswith("asmdb.delete:") for event in env.events)
    assert "blob.index" not in env.events


async def test_roundtrip_rollback_failure_is_loud_and_preserves_evidence() -> None:
    env = fake_environment()
    env.asmdb.corrupt_read_back = True
    env.asmdb.delete_error = AsmDbError("delete unavailable", code="unavailable")

    with pytest.raises(RollbackError, match="rollback was incomplete"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.asmdb.rows
    assert env.blob.cards[1] == b"png-1"


async def test_metadata_failure_retries_once_then_succeeds() -> None:
    env = fake_environment()
    env.generator.failures = [MetadataError("temporary metadata outage")]

    result = await run_daily(
        env.deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )

    assert result.status == "created"
    assert result.retries_consumed == 1
    assert len(env.generator.calls) == 2
    assert env.clock.sleeps == [2.0]


async def test_exhausted_metadata_failure_is_marked_retryable_without_persistence() -> None:
    env = fake_environment()
    env.generator.failures = [
        MetadataError("first"),
        MetadataError("second"),
    ]

    with pytest.raises(GenerationJobError) as caught:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert caught.value.kind == "metadata"
    assert caught.value.retryable is True
    assert env.blob.cards == {}
    assert env.asmdb.rows == {}


async def test_terminal_image_429_gets_one_job_level_backoff_retry() -> None:
    env = fake_environment()
    env.generator.failures = [
        ImageGenerationError("/images/edits failed after 5 attempts — last: HTTP 429")
    ]

    result = await run_daily(
        env.deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )

    assert result.retries_consumed == 1
    assert env.clock.sleeps == [60.0]
    assert len(env.generator.calls) == 2


async def test_exhausted_image_rate_limit_remains_retryable() -> None:
    env = fake_environment()
    env.generator.failures = [
        ImageGenerationError("last: HTTP 429"),
        ImageGenerationError("last: HTTP 429"),
    ]

    with pytest.raises(GenerationJobError) as caught:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert caught.value.kind == "image_rate_limit"
    assert caught.value.retryable is True
    assert caught.value.retries_consumed == 1
    assert env.blob.cards == {}


async def test_non_rate_limited_image_failure_is_not_retried() -> None:
    env = fake_environment()
    env.generator.failures = [ImageGenerationError("HTTP 400 invalid request")]

    with pytest.raises(GenerationJobError) as caught:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert caught.value.kind == "image"
    assert caught.value.retryable is False
    assert len(env.generator.calls) == 1


async def test_verification_failure_has_already_spent_its_one_regeneration() -> None:
    env = fake_environment()
    env.generator.failures = [VerificationError("still wrong")]

    with pytest.raises(GenerationJobError) as caught:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert caught.value.kind == "verification"
    assert caught.value.retryable is False
    assert len(env.generator.calls) == 1
    assert env.blob.cards == {}


@pytest.mark.parametrize(
    "failure",
    [RollError("bad roll"), PostProcessError("bad post-process")],
)
async def test_other_pipeline_failures_are_fatal_without_persistence(
    failure: Exception,
) -> None:
    env = fake_environment()
    env.generator.failures = [failure]

    with pytest.raises(GenerationJobError) as caught:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert caught.value.retryable is False
    assert env.blob.cards == {}


async def test_warm_failure_stops_before_the_business_date_lookup() -> None:
    env = fake_environment()
    env.asmdb.warm_error = AsmDbError("still starting", code="instance_starting")

    with pytest.raises(AsmDbError, match="still starting"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.events == ["asmdb.warm"]


async def test_blob_failure_leaves_database_empty() -> None:
    env = fake_environment()
    env.blob.put_error = OSError("blob unavailable")

    with pytest.raises(OSError, match="blob unavailable"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.asmdb.rows == {}
    assert "rows.write" not in env.events


async def test_database_failure_leaves_only_the_harmless_orphan_blob() -> None:
    env = fake_environment()
    env.asmdb.write_error = AsmDbError("write failed", code="unavailable")

    with pytest.raises(AsmDbError, match="write failed"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.blob.cards[1] == b"png-1"
    assert env.asmdb.rows == {}


async def test_index_failure_does_not_delete_an_already_verified_source_row() -> None:
    env = fake_environment()
    env.blob.index_error = OSError("index unavailable")

    with pytest.raises(OSError, match="index unavailable"):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    assert env.asmdb.rows
    assert env.blob.cards[1] == b"png-1"


async def test_success_and_step_metrics_are_structured() -> None:
    env = fake_environment()

    with capture_logs() as logs:
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    steps = [entry for entry in logs if entry.get("event") == "job.step.done"]
    success = next(entry for entry in logs if entry.get("event") == "daily.success")
    assert {entry["step"] for entry in steps} >= {
        "asmdb_warm",
        "idempotency",
        "serial_allocation",
        "generation",
        "blob_upload",
        "row_write",
        "round_trip",
        "index_refresh",
    }
    assert all("duration_ms" in entry for entry in steps)
    assert success["serial"] == 1
    assert success["rarity"] == "COMMON"
    assert success["retries_consumed"] == 0
    metric_names = [name for name, _value, _properties in env.metrics.records]
    assert "pixelslime.job.step.duration_ms" in metric_names
    assert "pixelslime.job.success" in metric_names
    assert "pixelslime.job.retries_consumed" in metric_names


async def test_failure_line_carries_the_allocated_serial() -> None:
    env = fake_environment()
    env.blob.put_error = OSError("blob unavailable")

    with capture_logs() as logs, pytest.raises(OSError):
        await run_daily(
            env.deps,
            now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
        )

    failure = next(entry for entry in logs if entry.get("event") == "daily.failure")
    assert failure["serial"] == 1
    assert failure["error_type"] == "OSError"
