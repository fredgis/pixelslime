"""The daily bloom clock.

``/api/cards/today`` counts down to the next bloom, and the countdown **must** use
the same boundary the daily job fires on, or the site and the job disagree about
which day it is. That boundary is 10:00 in ``Europe/Paris`` — the ``publishHour``
and ``timezone`` from ``contracts/design-tokens.json`` and the hour guard behind
the ``0 8,9 * * *`` UTC cron in ``infra`` (Container Apps cron is UTC-only).

DST is handled by never doing wall-clock arithmetic across a transition: we take
the target *calendar date*, then build 10:00 on that date **as a Paris-local
datetime** and let :mod:`zoneinfo` resolve the correct UTC offset. 10:00 is never
inside the spring-forward gap (01:00→03:00) or the autumn fold, so it is always a
single, unambiguous instant.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

#: Mirrors ``contracts/design-tokens.json`` → ``schedule`` and the ``infra`` cron.
PARIS = ZoneInfo("Europe/Paris")
PUBLISH_HOUR = 10

#: ``mint_day`` is days since this date (``contracts/card.schema.json``).
MINT_EPOCH = date(2026, 1, 1)


def mint_date(mint_day: int) -> date:
    """Map the codec's ``mint_day`` offset to a calendar date."""
    return MINT_EPOCH + timedelta(days=mint_day)


def yyyymmdd(day: date) -> int:
    """Render a date as the positive ``YYYYMMDD`` integer asmDB indexes on."""
    return day.year * 10000 + day.month * 100 + day.day


def paris_today(now_utc: datetime | None = None) -> date:
    """Return the current calendar date in ``Europe/Paris``."""
    moment = now_utc if now_utc is not None else datetime.now(tz=UTC)
    return moment.astimezone(PARIS).date()


def next_bloom_at(now_utc: datetime | None = None) -> datetime:
    """Return the next 10:00 ``Europe/Paris`` boundary, expressed in UTC.

    If the current Paris wall-clock time is before 10:00 today, the next bloom is
    today at 10:00; otherwise it is tomorrow at 10:00. Built on the calendar date
    (not by adding 24h to an aware datetime) so it stays correct across DST.
    """
    moment = now_utc if now_utc is not None else datetime.now(tz=UTC)
    now_paris = moment.astimezone(PARIS)
    target = _paris_ten(now_paris.date())
    if now_paris >= target:
        target = _paris_ten(now_paris.date() + timedelta(days=1))
    return target.astimezone(UTC)


def seconds_until_next_bloom(now_utc: datetime | None = None) -> int:
    """Whole seconds from now until the next bloom, never negative."""
    moment = now_utc if now_utc is not None else datetime.now(tz=UTC)
    delta = next_bloom_at(moment) - moment
    return max(0, int(delta.total_seconds()))


def _paris_ten(day: date) -> datetime:
    """10:00 on ``day`` as a Paris-local instant, DST resolved by zoneinfo."""
    return datetime(day.year, day.month, day.day, PUBLISH_HOUR, tzinfo=PARIS)


def iso_utc(moment: datetime) -> str:
    """Render an aware datetime as RFC3339 in UTC with a trailing ``Z``."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
