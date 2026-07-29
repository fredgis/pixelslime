"""Seed PS-0001 through PS-0004 and establish rarity exemplars."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from app.ai.postprocess import postprocess
from app.asmdb import AsmDbNotFound
from app.codec import Card, Flags
from app.core.logging import card_context, get_logger
from app.core.time import MINT_EPOCH, mint_date

from ._operations import (
    generate_with_policy,
    generation_context,
    persist_generated_card,
    read_card,
    read_collection,
    timed_step,
    yyyymmdd,
)
from .errors import JobError
from .models import GeneratedCard, JobDependencies

_log = get_logger(__name__)

# Curated seed dates immediately preceding Mochibo's contract date (mint_day 208).
# They remain stable business keys, and the normal daily card follows on day 209.
_LEGENDARY_MINT_DAY = 205
_COMMON_MINT_DAY = 206
_RARE_MINT_DAY = 207


@dataclass(frozen=True, slots=True)
class SeedAssets:
    """Read-only sources for the hand-curated and W4-generated seed art."""

    mochibo_card: Path
    mochibo_png: Path
    w4_summary: Path
    w4_legendary_png: Path


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Fixed serials created or already present and the W4 artefacts reused."""

    created: tuple[int, ...]
    skipped: tuple[int, ...]
    reused_w4: tuple[str, ...]
    retries_consumed: int


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "contracts" / "card.schema.json").is_file():
            return parent
    raise FileNotFoundError("could not locate contracts/card.schema.json")


def default_seed_assets() -> SeedAssets:
    """Resolve repository-owned seed inputs without depending on the process cwd."""
    root = _repo_root()
    return SeedAssets(
        mochibo_card=root / "contracts" / "cards" / "mochibo.json",
        mochibo_png=root / "assets" / "template" / "mochibo.png",
        w4_summary=root / "backend" / "tests" / "ai" / "output" / "summary.json",
        w4_legendary_png=root / "backend" / "tests" / "ai" / "output" / "legendary.png",
    )


def _seed_flags(flags: Flags) -> Flags:
    return flags.model_copy(update={"verified": True, "seed": True, "on_chain": False})


def _art_sha(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()[:8]


def _load_mochibo(assets: SeedAssets) -> GeneratedCard:
    png = assets.mochibo_png.read_bytes()
    derived = postprocess(png)
    card = Card.model_validate_json(assets.mochibo_card.read_text(encoding="utf-8"))
    card = card.model_copy(
        update={
            "serial": 1,
            "art_sha": derived.art_sha,
            "flags": _seed_flags(card.flags),
        }
    )
    return GeneratedCard(card=card, png_bytes=png, thumbnail_webp=derived.thumbnail_webp)


def _legendary_summary_card(summary: list[dict[str, Any]]) -> dict[str, Any]:
    for item in summary:
        if item.get("label") == "legendary":
            card = item.get("card")
            if isinstance(card, dict):
                return cast("dict[str, Any]", card)
    raise JobError("W4 summary does not contain the LEGENDARY seed card")


def _load_w4_legendary(assets: SeedAssets) -> GeneratedCard:
    raw = json.loads(assets.w4_summary.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise JobError("W4 summary root must be a list")
    png = assets.w4_legendary_png.read_bytes()
    derived = postprocess(png)
    payload = dict(_legendary_summary_card(raw))
    flags = dict(payload.get("flags", {}))
    flags.update(verified=True, seed=True, on_chain=False)
    payload.update(
        serial=2,
        mint_day=_LEGENDARY_MINT_DAY,
        rarity="LEGENDARY",
        art_sha=derived.art_sha,
        flags=flags,
    )
    card = Card.model_validate(payload)
    return GeneratedCard(card=card, png_bytes=png, thumbnail_webp=derived.thumbnail_webp)


async def _date_conflict(
    deps: JobDependencies,
    *,
    serial: int,
    mint_day: int,
) -> None:
    try:
        header = await deps.repository.find_card_by_date(yyyymmdd(mint_date(mint_day)))
    except AsmDbNotFound:
        return
    existing_serial = header.id // 16
    if existing_serial != serial:
        raise JobError(
            f"seed date {mint_date(mint_day).isoformat()} already belongs to "
            f"PS-{existing_serial:04d}"
        )


def _validate_existing(
    card: Card,
    *,
    serial: int,
    mint_day: int,
    rarity: str,
    name: str | None = None,
    art_sha: str | None = None,
) -> None:
    valid = (
        card.serial == serial
        and card.mint_day == mint_day
        and card.rarity == rarity
        and card.flags.seed
        and (name is None or card.name == name)
        and (art_sha is None or card.art_sha == art_sha)
    )
    if not valid:
        raise JobError(f"PS-{serial:04d} exists but is not the expected {rarity} seed")


async def _static_seed(
    deps: JobDependencies,
    *,
    generated: GeneratedCard,
    existing_serials: set[int],
    created: list[int],
    skipped: list[int],
) -> None:
    card = generated.card
    if card.serial in existing_serials:
        await _date_conflict(deps, serial=card.serial, mint_day=card.mint_day)
        stored = await read_card(deps, card.serial)
        _validate_existing(
            stored,
            serial=card.serial,
            mint_day=card.mint_day,
            rarity=card.rarity,
            name=card.name,
            art_sha=card.art_sha,
        )
        skipped.append(card.serial)
        return

    await _date_conflict(deps, serial=card.serial, mint_day=card.mint_day)
    with card_context(card.serial):
        await persist_generated_card(
            deps,
            generated,
            job="seed",
            mint_date=mint_date(card.mint_day),
        )
    existing_serials.add(card.serial)
    created.append(card.serial)


async def _generated_seed(
    deps: JobDependencies,
    *,
    serial: int,
    mint_day: int,
    rarity: str,
    existing_serials: set[int],
    created: list[int],
    skipped: list[int],
) -> int:
    if serial in existing_serials:
        await _date_conflict(deps, serial=serial, mint_day=mint_day)
        stored = await read_card(deps, serial)
        _validate_existing(
            stored,
            serial=serial,
            mint_day=mint_day,
            rarity=rarity,
        )
        skipped.append(serial)
        return 0

    await _date_conflict(deps, serial=serial, mint_day=mint_day)
    cards = await read_collection(deps, sorted(existing_serials))
    history, used_names = generation_context(cards)
    seed_date = mint_date(mint_day)
    with card_context(serial):
        with timed_step(
            deps,
            job="seed",
            step="generation",
            serial=serial,
            mint_date=seed_date,
        ):
            outcome = await generate_with_policy(
                deps,
                mint_day=mint_day,
                serial=serial,
                history=history,
                used_names=used_names,
                forced_rarity=rarity,
                is_seed=True,
            )
        card = outcome.generated.card
        if (
            card.serial != serial
            or card.mint_day != mint_day
            or card.rarity != rarity
            or not card.flags.seed
        ):
            raise JobError(f"pipeline did not return the requested {rarity} seed PS-{serial:04d}")
        await persist_generated_card(
            deps,
            outcome.generated,
            job="seed",
            mint_date=seed_date,
        )

    existing_serials.add(serial)
    created.append(serial)
    return outcome.retries_consumed


async def run_seed(
    deps: JobDependencies,
    *,
    assets: SeedAssets | None = None,
) -> SeedResult:
    """Install Mochibo, reuse W4's PS-0002 LEGENDARY, then generate two gaps.

    W4's COMMON image is not reusable: it visibly carries ``PS-0001``, which is
    reserved for Mochibo. Its LEGENDARY image already carries ``PS-0002`` and is
    therefore reused without another paid image request. COMMON PS-0003 and RARE
    PS-0004 are generated with forced rarities.
    """
    assets = assets or default_seed_assets()
    started = deps.monotonic()
    current_serial: int | None = None
    created: list[int] = []
    skipped: list[int] = []
    retries = 0

    try:
        with timed_step(
            deps,
            job="seed",
            step="asmdb_warm",
            serial=None,
            mint_date=MINT_EPOCH,
        ):
            await deps.control.warm()
        existing_serials = set(await deps.repository.list_card_serials())

        mochibo_png = assets.mochibo_png.read_bytes()
        if 1 in existing_serials:
            current_serial = 1
            await _date_conflict(deps, serial=1, mint_day=208)
            existing = await read_card(deps, 1)
            _validate_existing(
                existing,
                serial=1,
                mint_day=208,
                rarity="EPIC",
                name="Mochibo",
                art_sha=_art_sha(mochibo_png),
            )
            skipped.append(1)
        else:
            current_serial = 1
            await _static_seed(
                deps,
                generated=_load_mochibo(assets),
                existing_serials=existing_serials,
                created=created,
                skipped=skipped,
            )

        legendary_png = assets.w4_legendary_png.read_bytes()
        if 2 in existing_serials:
            current_serial = 2
            await _date_conflict(deps, serial=2, mint_day=_LEGENDARY_MINT_DAY)
            existing = await read_card(deps, 2)
            _validate_existing(
                existing,
                serial=2,
                mint_day=_LEGENDARY_MINT_DAY,
                rarity="LEGENDARY",
                name="Thundersnuggle",
                art_sha=_art_sha(legendary_png),
            )
            skipped.append(2)
        else:
            current_serial = 2
            await _static_seed(
                deps,
                generated=_load_w4_legendary(assets),
                existing_serials=existing_serials,
                created=created,
                skipped=skipped,
            )

        current_serial = 3
        retries += await _generated_seed(
            deps,
            serial=3,
            mint_day=_COMMON_MINT_DAY,
            rarity="COMMON",
            existing_serials=existing_serials,
            created=created,
            skipped=skipped,
        )
        current_serial = 4
        retries += await _generated_seed(
            deps,
            serial=4,
            mint_day=_RARE_MINT_DAY,
            rarity="RARE",
            existing_serials=existing_serials,
            created=created,
            skipped=skipped,
        )
    except Exception as exc:
        deps.metrics.record(
            "pixelslime.job.failure",
            1.0,
            {
                "job": "seed",
                "serial": current_serial,
                "error_type": type(exc).__name__,
            },
        )
        _log.error(
            "seed.failure",
            serial=current_serial,
            created=created,
            skipped=skipped,
            duration_ms=round((deps.monotonic() - started) * 1000, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise

    _log.info(
        "seed.success",
        serial=4,
        created=created,
        skipped=skipped,
        reused_w4=["LEGENDARY"],
        generated_rarities=["COMMON", "RARE"],
        retries_consumed=retries,
        duration_ms=round((deps.monotonic() - started) * 1000, 3),
    )
    deps.metrics.record(
        "pixelslime.job.success",
        1.0,
        {
            "job": "seed",
            "serial": 4,
            "created": len(created),
            "skipped": len(skipped),
            "retries_consumed": retries,
        },
    )
    deps.metrics.record(
        "pixelslime.job.retries_consumed",
        float(retries),
        {"job": "seed", "serial": 4},
    )
    return SeedResult(tuple(created), tuple(skipped), ("LEGENDARY",), retries)


async def _unwired_main() -> None:
    from .runtime import production_dependencies

    async with production_dependencies() as deps:
        await run_seed(deps)


def main() -> None:
    """Run the fixed, idempotent seed plan."""
    asyncio.run(_unwired_main())


if __name__ == "__main__":
    main()
