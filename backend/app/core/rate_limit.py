"""A cheap per-IP token-bucket rate limiter.

``docs/PLAN.md`` §7 asks only that a public site "cannot be trivially hammered".
An in-memory token bucket per client IP is enough: each IP gets ``capacity`` burst
tokens that refill at ``refill_per_second``. It is intentionally not distributed —
Container Apps may run a few replicas, so the effective limit is per-replica, which
is fine for abuse control and never rejects legitimate gallery browsing.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of one bucket check."""

    allowed: bool
    retry_after: float


class TokenBucketRateLimiter:
    """One refilling bucket per key (client IP), guarded by a single lock."""

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_buckets: int = 50_000,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive")
        self._capacity = float(capacity)
        self._refill = refill_per_second
        self._clock = clock
        self._max_buckets = max_buckets
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitResult:
        """Consume one token for ``key``; deny (with a retry hint) when empty."""
        async with self._lock:
            now = self._clock()
            tokens, last = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._refill)

            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                if len(self._buckets) > self._max_buckets:
                    self._prune(now)
                return RateLimitResult(allowed=True, retry_after=0.0)

            self._buckets[key] = (tokens, now)
            return RateLimitResult(allowed=False, retry_after=(1.0 - tokens) / self._refill)

    def _prune(self, now: float) -> None:
        """Drop buckets that have fully refilled — they carry no state worth keeping."""
        full = [
            key
            for key, (tokens, last) in self._buckets.items()
            if min(self._capacity, tokens + (now - last) * self._refill) >= self._capacity
        ]
        for key in full:
            del self._buckets[key]
