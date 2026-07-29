"""The daily-bloom clock, including the DST transitions that would break naive math."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.time import iso_utc, next_bloom_at, seconds_until_next_bloom


def _utc(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_winter_before_ten_is_today() -> None:
    # 08:00 UTC = 09:00 CET; next bloom is today 10:00 CET = 09:00 UTC.
    assert next_bloom_at(_utc(2026, 1, 15, 8)) == _utc(2026, 1, 15, 9)


def test_winter_after_ten_is_tomorrow() -> None:
    # 10:00 UTC = 11:00 CET; next bloom is tomorrow 10:00 CET = 09:00 UTC.
    assert next_bloom_at(_utc(2026, 1, 15, 10)) == _utc(2026, 1, 16, 9)


def test_summer_uses_cest_offset() -> None:
    # 07:00 UTC = 09:00 CEST; next bloom today 10:00 CEST = 08:00 UTC.
    assert next_bloom_at(_utc(2026, 7, 15, 7)) == _utc(2026, 7, 15, 8)


def test_summer_exactly_at_boundary_rolls_to_tomorrow() -> None:
    # 08:00 UTC = 10:00 CEST exactly; the next bloom is the following day.
    assert next_bloom_at(_utc(2026, 7, 15, 8)) == _utc(2026, 7, 16, 8)


def test_spring_forward_day_resolves_to_cest() -> None:
    # 2026-03-29 springs forward at 02:00→03:00; 10:00 local is CEST = 08:00 UTC.
    assert next_bloom_at(_utc(2026, 3, 29, 0, 30)) == _utc(2026, 3, 29, 8)


def test_autumn_fallback_day_resolves_to_cet() -> None:
    # 2026-10-25 falls back at 03:00→02:00; 10:00 local is CET = 09:00 UTC.
    assert next_bloom_at(_utc(2026, 10, 25, 0, 30)) == _utc(2026, 10, 25, 9)


def test_seconds_until_next_bloom_is_consistent() -> None:
    now = _utc(2026, 7, 15, 7)
    expected = int((next_bloom_at(now) - now).total_seconds())
    assert seconds_until_next_bloom(now) == expected
    assert expected == 3600  # one hour to 08:00 UTC


def test_iso_utc_uses_z_suffix() -> None:
    assert iso_utc(_utc(2026, 7, 15, 8)) == "2026-07-15T08:00:00Z"
