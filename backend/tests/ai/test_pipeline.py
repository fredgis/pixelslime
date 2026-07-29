"""End-to-end pipeline test with every network call mocked via respx."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from _helpers import (
    chat_response,
    image_edits_response,
    make_card_png,
    make_white_bordered_png,
    metadata_payload,
    tiny_png,
    vision_payload,
)
from conftest import CHAT_URL, IMAGES_URL

from app.ai.pipeline import generate_card
from app.ai.prompt import MasterPrompt
from app.ai.roll import roll

_MINT_DAY = 500
_SERIAL = 7


async def _no_sleep(_seconds: float) -> None:
    return None


def _template(tmp_path: Path) -> Path:
    (tmp_path / "mochibo.png").write_bytes(tiny_png())
    return tmp_path


def _card_view(card_type: str) -> dict[str, object]:
    payload = metadata_payload()
    return {
        "name": payload["name"],
        "level": payload["level"],
        "rarity": "COMMON",
        "type": card_type,
        "strength": payload["strength"],
        "endurance": payload["endurance"],
        "agility": payload["agility"],
        "happiness": payload["happiness"],
    }


@respx.mock
async def test_generate_card_happy_path(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    the_roll = roll(_MINT_DAY, forced_rarity="COMMON")
    good = make_card_png(seed=1)

    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_response(metadata_payload())),
            httpx.Response(200, json=chat_response(vision_payload(_card_view(the_roll.card_type)))),
        ]
    )
    respx.post(IMAGES_URL).mock(return_value=httpx.Response(200, json=image_edits_response(good)))

    result = await generate_card(
        mint_day=_MINT_DAY,
        serial=_SERIAL,
        client=client,
        master_prompt=master_prompt,
        template_dir=_template(tmp_path),
        reference_bytes=make_card_png(seed=2),
        forced_rarity="COMMON",
        is_seed=True,
        sleep=_no_sleep,
    )

    assert result.card["rarity"] == "COMMON"
    assert result.card["name"] == "Pebblory"
    assert result.card["type"] == the_roll.card_type
    assert result.card["frame_id"] == 0  # COMMON ordinal
    assert result.card["flags"]["verified"] is True
    assert result.card["flags"]["seed"] is True
    assert result.card["art_sha"] == result.post.art_sha
    assert result.png_bytes == good
    assert result.prompt_version == "v1"
    assert "COMMON" in result.image_prompt
    assert "WOODEN frame" in result.image_prompt
    assert result.verification.ok
    assert result.thumbnail_webp
    assert result.palette


@respx.mock
async def test_generate_card_regenerates_image_after_failed_verification(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    the_roll = roll(_MINT_DAY, forced_rarity="COMMON")
    good = make_card_png(seed=1)
    good_view = vision_payload(_card_view(the_roll.card_type))
    # Attempt 1 keys fine (it has a white margin) but the vision readback
    # disagrees with the JSON, so verification fails and the image is regenerated.
    bad_view = vision_payload(_card_view(the_roll.card_type), printed_name="Wrongname")

    chat = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_response(metadata_payload())),
            httpx.Response(200, json=chat_response(bad_view)),  # attempt 1: name mismatch
            httpx.Response(200, json=chat_response(good_view)),  # attempt 2: matches
        ]
    )
    images = respx.post(IMAGES_URL).mock(
        side_effect=[
            httpx.Response(200, json=image_edits_response(make_white_bordered_png())),
            httpx.Response(200, json=image_edits_response(good)),
        ]
    )

    result = await generate_card(
        mint_day=_MINT_DAY,
        serial=_SERIAL,
        client=client,
        master_prompt=master_prompt,
        template_dir=_template(tmp_path),
        reference_bytes=make_card_png(seed=2),
        forced_rarity="COMMON",
        sleep=_no_sleep,
    )

    assert images.call_count == 2  # first render failed verification, second passed
    assert chat.call_count == 3
    assert result.png_bytes == good
    assert result.verification.ok
