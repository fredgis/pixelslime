"""``python -m app.jobs`` dispatches without constructing unused resources."""

from __future__ import annotations

from app.jobs import __main__ as jobs_main


def test_package_cli_dispatches_daily(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[object] = []
    monkeypatch.setattr(jobs_main.daily, "main", lambda: calls.append("daily"))

    jobs_main.main(["daily"])

    assert calls == ["daily"]


def test_package_cli_forwards_backfill_dates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[object] = []
    monkeypatch.setattr(jobs_main.backfill, "main", lambda argv: calls.append(argv))

    jobs_main.main(["backfill", "2026-07-20", "2026-07-22"])

    assert calls == [["2026-07-20", "2026-07-22"]]


def test_package_cli_dispatches_seed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[object] = []
    monkeypatch.setattr(jobs_main.seed, "main", lambda: calls.append("seed"))

    jobs_main.main(["seed"])

    assert calls == ["seed"]
