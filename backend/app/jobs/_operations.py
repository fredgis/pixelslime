"""Shared orchestration primitives with the unsafe ordering encoded once."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

from app.ai import (
    GenerationError,
    ImageGenerationError,
    MetadataError,
    MintedCard,
    VerificationError,
)
from app.asmdb import AsmDbError, AsmDbNotFound
from app.asmdb import Row as AsmDbRow
from app.codec import Card, Row, card_hash, decode, encode
from app.core.index import CardIndex
from app.core.logging import get_logger
from app.core.time import MINT_EPOCH

from .errors import GenerationJobError, RollbackError, RoundTripError
from .models import GeneratedCard, JobDependencies

_log = get_logger(__name__)

METADATA_RETRIES = 1
METADATA_BACKOFF_SECONDS = 2.0
IMAGE_RATE_LIMIT_RETRIES = 1
IMAGE_RATE_LIMIT_BACKOFF_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class GenerationOutcome:
    """A generated card plus retries consumed outside W4's internal retries."""

    generated: GeneratedCard
    retries_consumed: int


def mint_day_for_date(day: date) -> int:
    """Map an operator-facing date onto the codec epoch without truncation."""
    mint_day = (day - MINT_EPOCH).days
    if not 0 <= mint_day <= 65535:
        raise ValueError(f"{day.isoformat()} is outside the PSC-1 mint_day range")
    return mint_day


def yyyymmdd(day: date) -> int:
    """Render the business key exactly as asmDB's positive header value."""
    return day.year * 10000 + day.month * 100 + day.day


@contextmanager
def timed_step(
    deps: JobDependencies,
    *,
    job: str,
    step: str,
    serial: int | None,
    mint_date: date,
) -> Iterator[None]:
    """Emit one numeric duration metric whether a step succeeds or fails."""
    started = deps.monotonic()
    try:
        yield
    except Exception as exc:
        duration_ms = round((deps.monotonic() - started) * 1000, 3)
        deps.metrics.record(
            "pixelslime.job.step.duration_ms",
            duration_ms,
            {
                "job": job,
                "step": step,
                "serial": serial,
                "mint_date": mint_date.isoformat(),
                "status": "failure",
                "error_type": type(exc).__name__,
            },
        )
        _log.error(
            "job.step.failed",
            job=job,
            step=step,
            serial=serial,
            mint_date=mint_date.isoformat(),
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    duration_ms = round((deps.monotonic() - started) * 1000, 3)
    deps.metrics.record(
        "pixelslime.job.step.duration_ms",
        duration_ms,
        {
            "job": job,
            "step": step,
            "serial": serial,
            "mint_date": mint_date.isoformat(),
            "status": "success",
        },
    )
    _log.info(
        "job.step.done",
        job=job,
        step=step,
        serial=serial,
        mint_date=mint_date.isoformat(),
        duration_ms=duration_ms,
    )


def to_asmdb_rows(rows: Iterable[Row]) -> list[AsmDbRow]:
    """Cross the codec/asmDB model boundary explicitly, preserving all payload bytes."""
    return [AsmDbRow(id=row.id, value=row.value, tag=row.tag, content=row.content) for row in rows]


def to_codec_rows(rows: Iterable[AsmDbRow]) -> list[Row]:
    """Discard engine timestamps before the canonical PSC-1 decode."""
    return [Row(id=row.id, value=row.value, tag=row.tag, content=row.content) for row in rows]


async def read_card(deps: JobDependencies, serial: int) -> Card:
    """Read through W3 and decode through W2 so history uses canonical state."""
    return decode(to_codec_rows(await deps.repository.read_card_rows(serial)))


async def read_collection(
    deps: JobDependencies,
    serials: Sequence[int],
) -> list[Card]:
    """Load existing cards for name uniqueness and the rarity pity timer."""
    return [await read_card(deps, serial) for serial in serials]


def generation_context(cards: Sequence[Card]) -> tuple[list[MintedCard], list[str]]:
    """Project stored cards onto the two historical inputs W4 consumes."""
    return (
        [MintedCard(mint_day=card.mint_day, rarity=card.rarity) for card in cards],
        [card.name for card in cards],
    )


def _is_image_rate_limit(exc: ImageGenerationError) -> bool:
    message = str(exc).casefold()
    return "http 429" in message or "rate limit" in message or "rate-limit" in message


async def generate_with_policy(
    deps: JobDependencies,
    *,
    mint_day: int,
    serial: int,
    history: Sequence[MintedCard],
    used_names: Sequence[str],
    forced_rarity: str | None = None,
    is_seed: bool = False,
) -> GenerationOutcome:
    """Add only the job-level retries W4 cannot perform at its pure boundary.

    W4 already re-prompts invalid metadata, backs off transient image responses,
    and regenerates one failed verification. This wrapper retries a terminal
    metadata failure once and a terminal 429 once; a verification failure has
    already spent its single regeneration and is therefore raised immediately.
    """
    metadata_retries = 0
    image_retries = 0
    total_retries = 0

    while True:
        try:
            generated = await deps.generator(
                mint_day=mint_day,
                serial=serial,
                history=history,
                used_names=used_names,
                forced_rarity=forced_rarity,
                is_seed=is_seed,
            )
        except MetadataError as exc:
            if metadata_retries >= METADATA_RETRIES:
                raise GenerationJobError(
                    f"metadata generation failed for card {serial}",
                    kind="metadata",
                    retryable=True,
                    retries_consumed=total_retries,
                ) from exc
            wait = METADATA_BACKOFF_SECONDS * (2**metadata_retries)
            metadata_retries += 1
        except ImageGenerationError as exc:
            if not _is_image_rate_limit(exc):
                raise GenerationJobError(
                    f"image generation failed for card {serial}",
                    kind="image",
                    retryable=False,
                    retries_consumed=total_retries,
                ) from exc
            if image_retries >= IMAGE_RATE_LIMIT_RETRIES:
                raise GenerationJobError(
                    f"image rate limit persisted for card {serial}",
                    kind="image_rate_limit",
                    retryable=True,
                    retries_consumed=total_retries,
                ) from exc
            wait = IMAGE_RATE_LIMIT_BACKOFF_SECONDS * (2**image_retries)
            image_retries += 1
        except VerificationError as exc:
            raise GenerationJobError(
                f"verification failed after W4's regeneration for card {serial}",
                kind="verification",
                retryable=False,
                retries_consumed=total_retries,
            ) from exc
        except GenerationError as exc:
            raise GenerationJobError(
                f"generation failed for card {serial}",
                kind=type(exc).__name__,
                retryable=False,
                retries_consumed=total_retries,
            ) from exc
        else:
            return GenerationOutcome(generated=generated, retries_consumed=total_retries)

        total_retries += 1
        _log.warning(
            "generation.retry",
            serial=serial,
            retry=total_retries,
            wait_seconds=wait,
            metadata_retries=metadata_retries,
            image_rate_limit_retries=image_retries,
        )
        deps.metrics.record(
            "pixelslime.job.generation_retry",
            1.0,
            {
                "serial": serial,
                "retry": total_retries,
                "metadata_retries": metadata_retries,
                "image_rate_limit_retries": image_retries,
            },
        )
        await deps.sleep(wait)


async def _rollback_rows(
    deps: JobDependencies,
    *,
    serial: int,
    row_ids: Iterable[int],
) -> None:
    errors: list[str] = []
    for row_id in reversed(tuple(row_ids)):
        try:
            await deps.control.delete(row_id)
        except AsmDbNotFound:
            continue
        except AsmDbError as exc:
            errors.append(f"row {row_id}: {exc}")
    if errors:
        raise RollbackError(
            f"card {serial} semantic round-trip failed and rollback was incomplete: "
            + "; ".join(errors)
        )


async def refresh_index(deps: JobDependencies) -> int:
    """Rebuild the blob projection from authoritative rows after a safe write."""
    serials = await deps.repository.list_card_serials()
    cards = await read_collection(deps, serials)
    index = CardIndex()
    index.replace_all(cards)
    await deps.blob.save_index(index.to_json_bytes())
    return index.size


async def persist_generated_card(
    deps: JobDependencies,
    generated: GeneratedCard,
    *,
    job: str,
    mint_date: date,
) -> None:
    """Publish blob-first, then rows, then enforce a semantic read-back.

    W3's ``write_card_rows`` already rolls back a partial or payload-divergent
    multi-row write. The extra compensation here is intentionally narrower: it
    runs only if the subsequent full PSC-1 decode differs from the generated
    canonical card.
    """
    card = generated.card
    rows = to_asmdb_rows(encode(card))

    with timed_step(deps, job=job, step="blob_upload", serial=card.serial, mint_date=mint_date):
        await deps.blob.put_card(card.serial, generated.png_bytes, generated.thumbnail_webp)

    with timed_step(deps, job=job, step="row_write", serial=card.serial, mint_date=mint_date):
        await deps.repository.write_card_rows(rows)

    try:
        with timed_step(
            deps,
            job=job,
            step="round_trip",
            serial=card.serial,
            mint_date=mint_date,
        ):
            actual = await read_card(deps, card.serial)
            if actual != card:
                raise RoundTripError(
                    f"card {card.serial} decoded state diverged from generated state"
                )
    except Exception as exc:
        await _rollback_rows(deps, serial=card.serial, row_ids=(row.id for row in rows))
        if isinstance(exc, RoundTripError):
            raise
        raise RoundTripError(f"card {card.serial} could not complete semantic read-back") from exc

    with timed_step(deps, job=job, step="index_refresh", serial=card.serial, mint_date=mint_date):
        cards = await refresh_index(deps)

    _log.info(
        "card.persisted",
        job=job,
        serial=card.serial,
        mint_date=mint_date.isoformat(),
        rarity=card.rarity,
        rows=len(rows),
        cards_in_index=cards,
        card_hash=card_hash(card).hex(),
    )
    deps.metrics.record(
        "pixelslime.index.cards",
        float(cards),
        {"job": job, "serial": card.serial, "rarity": card.rarity},
    )
