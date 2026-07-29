"""The end-to-end generation pipeline: roll → metadata → image → verify → post.

This orchestrates steps 1-5 of ``docs/PLAN.md`` §5 and returns a validated card
dict plus the image bytes. It is deliberately **pure of side effects**: it never
uploads a blob, writes asmDB, or mints on-chain — steps 6/7 belong to W8/W9. That
keeps the creative pipeline testable offline and re-runnable without touching any
external system.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx
import structlog

from .config import STYLE_ID, assets_template_dir, rarity_ordinal
from .errors import VerificationError
from .imagegen import Sleeper, build_image_prompt, generate_image
from .metadata import CardText, generate_metadata
from .models import Card, CardTypeName, Flags, RarityName
from .postprocess import PostProcessResult, postprocess
from .prompt import MasterPrompt, load_master_prompt
from .roll import MintedCard, Roll, roll
from .verify import VerificationResult, verify_card

_log = structlog.get_logger("app.ai.pipeline")

#: How many times the image may be regenerated after a failed verification
#: before the pipeline gives up (``docs/PLAN.md`` §5: "no, one more attempt").
VERIFY_RETRIES = 1


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Everything step 5 produces for one card (nothing persisted)."""

    card: dict[str, Any]
    card_model: Card
    png_bytes: bytes
    roll: Roll
    text: CardText
    verification: VerificationResult
    post: PostProcessResult
    prompt_version: str
    image_prompt: str

    @property
    def thumbnail_webp(self) -> bytes:
        return self.post.thumbnail_webp

    @property
    def palette(self) -> list[str]:
        return self.post.palette


def _assemble_card(
    serial: int,
    mint_day: int,
    the_roll: Roll,
    text: CardText,
    *,
    is_seed: bool,
    verified: bool = False,
    art_sha: str | None = None,
) -> Card:
    """Build and validate a full card from the roll and the written text."""
    return Card(
        serial=serial,
        name=text.name,
        level=text.level,
        rarity=cast(RarityName, the_roll.rarity),
        card_type=cast(CardTypeName, the_roll.card_type),
        height_mm=text.height_mm,
        weight_g=text.weight_g,
        strength=text.strength,
        endurance=text.endurance,
        agility=text.agility,
        happiness=text.happiness,
        art_id=the_roll.art_id,
        style_id=STYLE_ID,
        frame_id=rarity_ordinal(the_roll.rarity),
        background_id=the_roll.background_id,
        biome_id=the_roll.biome_id,
        mood_id=the_roll.mood_id,
        personality=text.personality,
        power_name=text.power_name,
        power_desc=text.power_desc,
        quote=text.quote,
        mint_day=mint_day,
        shiny=the_roll.shiny,
        flags=Flags(
            has_companion=the_roll.has_companion,
            has_accessory=the_roll.has_accessory,
            verified=verified,
            on_chain=False,
            seed=is_seed,
        ),
        art_sha=art_sha,
        biome=the_roll.biome,
        companion=the_roll.companion,
    )


async def generate_card(
    *,
    mint_day: int,
    serial: int,
    client: httpx.AsyncClient,
    master_prompt: MasterPrompt | None = None,
    history: Sequence[MintedCard] = (),
    used_names: Sequence[str] = (),
    template_dir: Path | None = None,
    reference_bytes: bytes | None = None,
    forced_rarity: str | None = None,
    is_seed: bool = False,
    run_vision: bool = True,
    verify_retries: int = VERIFY_RETRIES,
    sleep: Sleeper = asyncio.sleep,
) -> PipelineResult:
    """Run the full pipeline for one card and return the validated result.

    ``forced_rarity`` pins the tier (used to hand-seed the reference exemplars);
    ``is_seed`` marks the card as hand-seeded in its flags. The image is
    regenerated up to ``verify_retries`` times if verification fails; a persistent
    failure raises ``VerificationError`` so the daily job can alert rather than
    publish a half-wrong card.
    """
    prompt = master_prompt or load_master_prompt()
    directory = template_dir or assets_template_dir()
    if reference_bytes is None:
        reference_bytes = (directory / "mochibo.png").read_bytes()

    log = _log.bind(serial=serial, mint_day=mint_day, prompt_version=prompt.version)

    the_roll = roll(mint_day, history, forced_rarity=forced_rarity)
    log.info(
        "roll.done",
        rarity=the_roll.rarity,
        card_type=the_roll.card_type,
        pity_forced=the_roll.pity_forced,
        seed=the_roll.seed,
    )

    text = await generate_metadata(the_roll, used_names, client=client, master_prompt=prompt)
    log.info("metadata.done", name=text.name, level=text.level)

    base_card = _assemble_card(serial, mint_day, the_roll, text, is_seed=is_seed)
    card_dict = base_card.model_dump(by_alias=True)
    image_prompt = build_image_prompt(prompt, card_dict, the_roll)

    verification: VerificationResult | None = None
    png_bytes = b""
    for attempt in range(verify_retries + 1):
        png_bytes = await generate_image(
            card_dict,
            the_roll,
            client=client,
            master_prompt=prompt,
            template_dir=template_dir,
            prompt=image_prompt,
            sleep=sleep,
        )
        verification = await verify_card(
            png_bytes,
            card_dict,
            client=client,
            reference_bytes=reference_bytes,
            run_vision=run_vision,
        )
        if verification.ok:
            log.info("verify.ok", attempt=attempt, similarity=verification.similarity_score)
            break
        log.warning("verify.failed", attempt=attempt, reasons=verification.reasons)
    else:
        assert verification is not None
        raise VerificationError(
            f"card {serial} failed verification after {verify_retries + 1} attempts",
            reasons=verification.reasons,
        )

    assert verification is not None
    post = postprocess(png_bytes)
    log.info("postprocess.done", art_sha=post.art_sha, palette=post.palette)

    final_card = _assemble_card(
        serial,
        mint_day,
        the_roll,
        text,
        is_seed=is_seed,
        verified=True,
        art_sha=post.art_sha,
    )

    return PipelineResult(
        card=final_card.model_dump(by_alias=True, exclude_none=True),
        card_model=final_card,
        png_bytes=png_bytes,
        roll=the_roll,
        text=text,
        verification=verification,
        post=post,
        prompt_version=prompt.version,
        image_prompt=image_prompt,
    )
