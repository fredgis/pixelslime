"""Container Apps Job entrypoint for one punctual, idempotent daily bloom."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

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
_PARIS = ZoneInfo("Europe/Paris")


@dataclass(frozen=True, slots=True)
class DailyResult:
    """Observable outcome used by the CLI, tests and manual reruns."""

    status: Literal["stood_down", "already_exists", "created"]
    mint_date: date
    serial: int | None
    retries_consumed: int = 0


async def run_daily(
    deps: JobDependencies,
    *,
    now_utc: datetime | None = None,
) -> DailyResult:
    """Publish only at the Paris 10:00 wall-clock boundary.

    The UTC cron deliberately fires twice; this guard makes one run inert, while
    the date lookup makes every retry or redeploy safe.
    """
    now_paris = datetime.now(_PARIS) if now_utc is None else now_utc.astimezone(_PARIS)
    mint_date = now_paris.date()
    if now_paris.hour != 10:
        _log.info("not 10:00 in Paris yet, standing down")
        deps.metrics.record(
            "pixelslime.job.stood_down",
            1.0,
            {"job": "daily", "mint_date": mint_date.isoformat()},
        )
        return DailyResult(status="stood_down", mint_date=mint_date, serial=None)

    started = deps.monotonic()
    serial: int | None = None
    try:
        with timed_step(
            deps,
            job="daily",
            step="asmdb_warm",
            serial=None,
            mint_date=mint_date,
        ):
            await deps.control.warm()

        business_date = yyyymmdd(mint_date)
        with timed_step(
            deps,
            job="daily",
            step="idempotency",
            serial=None,
            mint_date=mint_date,
        ):
            try:
                existing = await deps.repository.find_card_by_date(business_date)
            except AsmDbNotFound:
                existing = None
        if existing is not None:
            serial = existing.id // 16
            _log.info(
                "daily.already_exists",
                serial=serial,
                mint_date=mint_date.isoformat(),
                duration_ms=round((deps.monotonic() - started) * 1000, 3),
            )
            deps.metrics.record(
                "pixelslime.job.already_exists",
                1.0,
                {
                    "job": "daily",
                    "serial": serial,
                    "mint_date": mint_date.isoformat(),
                },
            )
            return DailyResult(
                status="already_exists",
                mint_date=mint_date,
                serial=serial,
            )

        with timed_step(
            deps,
            job="daily",
            step="serial_allocation",
            serial=None,
            mint_date=mint_date,
        ):
            serials = await deps.repository.list_card_serials()
            serial = max(serials, default=0) + 1
            if serial > 65535:
                raise RuntimeError("PSC-1 serial space is exhausted")
            existing_cards = await read_collection(deps, serials)
            history, used_names = generation_context(existing_cards)

        with card_context(serial):
            with timed_step(
                deps,
                job="daily",
                step="generation",
                serial=serial,
                mint_date=mint_date,
            ):
                outcome = await generate_with_policy(
                    deps,
                    mint_day=mint_day_for_date(mint_date),
                    serial=serial,
                    history=history,
                    used_names=used_names,
                )

            await persist_generated_card(
                deps,
                outcome.generated,
                job="daily",
                mint_date=mint_date,
            )

        duration_ms = round((deps.monotonic() - started) * 1000, 3)
        _log.info(
            "daily.success",
            serial=serial,
            mint_date=mint_date.isoformat(),
            rarity=outcome.generated.card.rarity,
            retries_consumed=outcome.retries_consumed,
            duration_ms=duration_ms,
        )
        deps.metrics.record(
            "pixelslime.job.success",
            1.0,
            {
                "job": "daily",
                "serial": serial,
                "mint_date": mint_date.isoformat(),
                "rarity": outcome.generated.card.rarity,
                "retries_consumed": outcome.retries_consumed,
            },
        )
        deps.metrics.record(
            "pixelslime.job.retries_consumed",
            float(outcome.retries_consumed),
            {"job": "daily", "serial": serial},
        )
        return DailyResult(
            status="created",
            mint_date=mint_date,
            serial=serial,
            retries_consumed=outcome.retries_consumed,
        )
    except Exception as exc:
        duration_ms = round((deps.monotonic() - started) * 1000, 3)
        deps.metrics.record(
            "pixelslime.job.failure",
            1.0,
            {
                "job": "daily",
                "serial": serial,
                "mint_date": mint_date.isoformat(),
                "error_type": type(exc).__name__,
            },
        )
        _log.error(
            "daily.failure",
            serial=serial,
            mint_date=mint_date.isoformat(),
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise


async def _unwired_main() -> None:
    """Compatibility wrapper for the module entrypoint."""
    await run_scheduled()


async def run_scheduled(*, now_utc: datetime | None = None) -> DailyResult:
    """Apply the Paris guard before secrets, clients or Azure SDKs are constructed."""
    now_paris = datetime.now(_PARIS) if now_utc is None else now_utc.astimezone(_PARIS)
    if now_paris.hour != 10:
        _log.info("not 10:00 in Paris yet, standing down")
        return DailyResult(status="stood_down", mint_date=now_paris.date(), serial=None)

    from .runtime import production_dependencies

    async with production_dependencies() as deps:
        return await run_daily(deps, now_utc=now_paris)


def main() -> None:
    """Run the scheduled command and let any failure produce a non-zero exit."""
    asyncio.run(_unwired_main())


if __name__ == "__main__":
    main()
