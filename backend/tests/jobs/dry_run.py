"""Executable end-to-end daily run against the jobs' real in-memory fakes."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from _jobs_helpers import fake_environment  # noqa: E402

from app.jobs.daily import run_daily  # noqa: E402


async def _run() -> None:
    env = fake_environment()
    deps = replace(env.deps, monotonic=time.perf_counter, sleep=asyncio.sleep)
    result = await run_daily(
        deps,
        now_utc=datetime(2026, 7, 29, 8, tzinfo=UTC),
    )
    print(
        json.dumps(
            {
                "dry_run": "complete",
                "status": result.status,
                "serial": result.serial,
                "events": env.events,
                "rows": sorted(env.asmdb.rows),
                "index_bytes": len(env.blob.index or b""),
                "metrics": len(env.metrics.records),
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    asyncio.run(_run())
