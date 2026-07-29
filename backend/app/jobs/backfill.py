"""Operator command for safely filling an inclusive range of missed bloom days."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from app.ai.config import IMAGE_MIN_SPACING_SECONDS
from app.asmdb import AsmDbNotFound
from app.core.logging import card_context, get_logger

from ._operations import (
    generate_with_policy,
    generation_context,
    mint_day_for_date,
    persist_generated_card,
    read_collection,
    timed_step,
    yyyymmdd,
)
from .models import JobDependencies

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BackfillResult:
    """Dates created and skipped, preserving processing order for operators."""

    created: tuple[tuple[date, int], ...]
    skipped: tuple[tuple[date, int], ...]
    retries_consumed: int


def _dates(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("start date must be on or before end date")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


async def run_backfill(
    deps: JobDependencies,
    *,
    start: date,
    end: date,
) -> BackfillResult:
    """Create each absent business date once, spacing generation starts by 35s.

    The production AI client additionally gates every individual image HTTP
    request. The inter-card spacing here remains valuable for injected generators
    and ensures a normal one-image card cannot burst past two starts per minute.
    """
    days = _dates(start, end)
    started = deps.monotonic()
    current_serial: int | None = None
    created: list[tuple[date, int]] = []
    skipped: list[tuple[date, int]] = []
    total_retries = 0
    last_generation_at: float | None = None

    try:
        with timed_step(
            deps,
            job="backfill",
            step="asmdb_warm",
            serial=None,
            mint_date=start,
        ):
            await deps.control.warm()

        for mint_date in days:
            current_serial = None
            with timed_step(
                deps,
                job="backfill",
                step="idempotency",
                serial=None,
                mint_date=mint_date,
            ):
                try:
                    existing = await deps.repository.find_card_by_date(yyyymmdd(mint_date))
                except AsmDbNotFound:
                    existing = None
            if existing is not None:
                existing_serial = existing.id // 16
                skipped.append((mint_date, existing_serial))
                _log.info(
                    "backfill.skipped",
                    serial=existing_serial,
                    mint_date=mint_date.isoformat(),
                )
                continue

            with timed_step(
                deps,
                job="backfill",
                step="serial_allocation",
                serial=None,
                mint_date=mint_date,
            ):
                serials = await deps.repository.list_card_serials()
                current_serial = max(serials, default=0) + 1
                if current_serial > 65535:
                    raise RuntimeError("PSC-1 serial space is exhausted")
                cards = await read_collection(deps, serials)
                history, used_names = generation_context(cards)

            if last_generation_at is not None:
                delay = last_generation_at + IMAGE_MIN_SPACING_SECONDS - deps.monotonic()
                if delay > 0:
                    _log.info(
                        "backfill.rate_limit_wait",
                        serial=current_serial,
                        mint_date=mint_date.isoformat(),
                        wait_seconds=round(delay, 3),
                    )
                    await deps.sleep(delay)
            last_generation_at = deps.monotonic()

            with card_context(current_serial):
                with timed_step(
                    deps,
                    job="backfill",
                    step="generation",
                    serial=current_serial,
                    mint_date=mint_date,
                ):
                    outcome = await generate_with_policy(
                        deps,
                        mint_day=mint_day_for_date(mint_date),
                        serial=current_serial,
                        history=history,
                        used_names=used_names,
                    )
                await persist_generated_card(
                    deps,
                    outcome.generated,
                    job="backfill",
                    mint_date=mint_date,
                )

            created.append((mint_date, current_serial))
            total_retries += outcome.retries_consumed
            _log.info(
                "backfill.card_success",
                serial=current_serial,
                mint_date=mint_date.isoformat(),
                rarity=outcome.generated.card.rarity,
                retries_consumed=outcome.retries_consumed,
            )
            deps.metrics.record(
                "pixelslime.job.success",
                1.0,
                {
                    "job": "backfill",
                    "serial": current_serial,
                    "mint_date": mint_date.isoformat(),
                    "rarity": outcome.generated.card.rarity,
                    "retries_consumed": outcome.retries_consumed,
                },
            )
    except Exception as exc:
        deps.metrics.record(
            "pixelslime.job.failure",
            1.0,
            {
                "job": "backfill",
                "serial": current_serial,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "error_type": type(exc).__name__,
            },
        )
        _log.error(
            "backfill.failure",
            serial=current_serial,
            start=start.isoformat(),
            end=end.isoformat(),
            created=len(created),
            skipped=len(skipped),
            duration_ms=round((deps.monotonic() - started) * 1000, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    _log.info(
        "backfill.success",
        serial=created[-1][1] if created else None,
        start=start.isoformat(),
        end=end.isoformat(),
        created=len(created),
        skipped=len(skipped),
        retries_consumed=total_retries,
        duration_ms=round((deps.monotonic() - started) * 1000, 3),
    )
    deps.metrics.record(
        "pixelslime.job.retries_consumed",
        float(total_retries),
        {"job": "backfill", "created": len(created), "skipped": len(skipped)},
    )
    return BackfillResult(tuple(created), tuple(skipped), total_retries)


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


async def _unwired_main(start: date, end: date) -> None:
    from .runtime import production_dependencies

    async with production_dependencies() as deps:
        await run_backfill(deps, start=start, end=end)


def main(argv: list[str] | None = None) -> None:
    """Run an inclusive ``START END`` range and fail non-zero on any bad day."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("start", type=_date_arg)
    parser.add_argument("end", type=_date_arg)
    args = parser.parse_args(argv)
    asyncio.run(_unwired_main(args.start, args.end))


if __name__ == "__main__":
    main()
