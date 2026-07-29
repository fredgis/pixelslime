"""Tests for the image step: reference strategy, multipart shape, prompt, backoff."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
import respx
from _ai_helpers import (
    image_edits_response,
    make_white_bordered_png,
    tiny_png,
    valid_card_dict,
)
from conftest import IMAGES_URL
from PIL import Image

from app.ai.config import (
    CARD_SIZE,
    IMAGE_BACKGROUND,
    IMAGE_MODEL,
    IMAGE_OUTPUT_FORMAT,
    IMAGE_QUALITY,
)
from app.ai.errors import ImageGenerationError
from app.ai.imagegen import (
    background_to_alpha,
    build_image_prompt,
    build_request,
    generate_image,
    resolve_references,
)
from app.ai.prompt import MasterPrompt
from app.ai.roll import roll

_ROLL = roll(200, forced_rarity="COMMON")


class _Sleeps:
    """An injectable async sleep that records the waits it was asked to make."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _template_dir(tmp_path: Path, *, extra: dict[str, bytes] | None = None) -> Path:
    (tmp_path / "mochibo.png").write_bytes(tiny_png())
    for name, data in (extra or {}).items():
        (tmp_path / name).write_bytes(data)
    return tmp_path


def test_resolve_references_single_when_no_exemplar(tmp_path: Path) -> None:
    refs = resolve_references("COMMON", template_dir=_template_dir(tmp_path))
    assert [p.name for p in refs] == ["mochibo.png"]


def test_resolve_references_appends_distinct_exemplar(tmp_path: Path) -> None:
    directory = _template_dir(tmp_path, extra={"ref-common.png": tiny_png()})
    refs = resolve_references("COMMON", template_dir=directory)
    assert [p.name for p in refs] == ["mochibo.png", "ref-common.png"]  # canon first


def test_resolve_references_missing_canon_raises(tmp_path: Path) -> None:
    with pytest.raises(ImageGenerationError, match="anatomy canon"):
        resolve_references("COMMON", template_dir=tmp_path)


def test_build_request_uses_plural_image_field_with_canon_present(tmp_path: Path) -> None:
    refs = resolve_references("COMMON", template_dir=_template_dir(tmp_path))
    data, files = build_request("PROMPT", refs, n=1)

    assert all(field == "image[]" for field, _ in files)  # plural, never singular
    assert any(payload[0] == "mochibo.png" for _, payload in files)  # canon always sent
    assert data["model"] == IMAGE_MODEL
    assert data["size"] == CARD_SIZE == "1024x1536"
    assert data["background"] == IMAGE_BACKGROUND == "auto"
    assert data["output_format"] == IMAGE_OUTPUT_FORMAT == "png"
    assert data["quality"] == IMAGE_QUALITY == "high"
    assert data["n"] == "1"


def test_build_request_sends_two_files_when_exemplar_present(tmp_path: Path) -> None:
    directory = _template_dir(tmp_path, extra={"ref-common.png": tiny_png()})
    refs = resolve_references("COMMON", template_dir=directory)
    _data, files = build_request("PROMPT", refs)
    assert [payload[0] for _, payload in files] == ["mochibo.png", "ref-common.png"]
    assert all(field == "image[]" for field, _ in files)


def test_image_prompt_spells_out_common_finish_and_less_ornate(
    master_prompt: MasterPrompt,
) -> None:
    card = valid_card_dict(rarity="COMMON")
    prompt = build_image_prompt(master_prompt, card, _ROLL)

    assert card["name"] in prompt
    assert "COMMON" in prompt
    assert "WOODEN frame" in prompt  # the COMMON finish
    assert "LESS ornate" in prompt  # the sub-EPIC contrast (risk R12)
    assert "FLAT, SOLID, UNIFORM WHITE" in prompt  # the keyable exterior (model can't do alpha)
    assert "keys that white to real" in prompt  # transparency recovered in post
    assert "LAYOUT" in prompt  # reference == layout, not the creature
    assert "do NOT define the creature" in prompt


def test_image_prompt_marks_legendary_as_more_exceptional(master_prompt: MasterPrompt) -> None:
    card = valid_card_dict(rarity="LEGENDARY", frame_id=4)
    prompt = build_image_prompt(master_prompt, card, roll(200, forced_rarity="LEGENDARY"))
    assert "LEGENDARY" in prompt
    assert "MORE" in prompt  # higher-than-EPIC contrast
    assert "LESS ornate" not in prompt


@respx.mock
async def test_generate_image_returns_decoded_png(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    png = tiny_png()
    route = respx.post(IMAGES_URL).mock(
        return_value=httpx.Response(200, json=image_edits_response(png))
    )
    out = await generate_image(
        valid_card_dict(),
        _ROLL,
        client=client,
        master_prompt=master_prompt,
        template_dir=_template_dir(tmp_path),
        prompt="PROMPT",
        recover_alpha=False,  # this test is about decoding, not keying
    )
    assert out == png
    assert route.call_count == 1


@respx.mock
async def test_generate_image_recovers_transparent_background(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    # The model returns an opaque white-bordered card; generate_image must key it.
    respx.post(IMAGES_URL).mock(
        return_value=httpx.Response(200, json=image_edits_response(make_white_bordered_png()))
    )
    out = await generate_image(
        valid_card_dict(),
        _ROLL,
        client=client,
        master_prompt=master_prompt,
        template_dir=_template_dir(tmp_path),
        prompt="PROMPT",
    )
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    w, h = img.size
    alpha = img.getchannel("A")
    corners = [
        alpha.getpixel((0, 0)),
        alpha.getpixel((w - 1, 0)),
        alpha.getpixel((0, h - 1)),
        alpha.getpixel((w - 1, h - 1)),
    ]
    assert corners == [0, 0, 0, 0]  # exterior keyed to real transparency
    assert alpha.getpixel((w // 2, h // 2)) == 255  # card body stays opaque


@respx.mock
async def test_generate_image_honours_retry_after_then_succeeds(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    png = tiny_png()
    respx.post(IMAGES_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}, text="slow down"),
            httpx.Response(200, json=image_edits_response(png)),
        ]
    )
    sleeps = _Sleeps()
    out = await generate_image(
        valid_card_dict(),
        _ROLL,
        client=client,
        master_prompt=master_prompt,
        template_dir=_template_dir(tmp_path),
        prompt="PROMPT",
        recover_alpha=False,
        sleep=sleeps,
    )
    assert out == png
    assert sleeps.calls == [7.0]  # waited exactly the server-asked interval


@respx.mock
async def test_generate_image_non_retryable_4xx_raises_at_once(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    respx.post(IMAGES_URL).mock(return_value=httpx.Response(400, text="bad prompt"))
    sleeps = _Sleeps()
    with pytest.raises(ImageGenerationError, match="not retryable"):
        await generate_image(
            valid_card_dict(),
            _ROLL,
            client=client,
            master_prompt=master_prompt,
            template_dir=_template_dir(tmp_path),
            prompt="PROMPT",
            sleep=sleeps,
        )
    assert sleeps.calls == []  # a genuine bad request is not hammered


@respx.mock
async def test_generate_image_exhausts_attempts_on_persistent_5xx(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    respx.post(IMAGES_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    sleeps = _Sleeps()
    with pytest.raises(ImageGenerationError, match="after 3 attempts"):
        await generate_image(
            valid_card_dict(),
            _ROLL,
            client=client,
            master_prompt=master_prompt,
            template_dir=_template_dir(tmp_path),
            prompt="PROMPT",
            max_attempts=3,
            sleep=sleeps,
        )
    assert len(sleeps.calls) == 2  # slept between attempts, not after the last


@respx.mock
async def test_generate_image_rejects_malformed_success_body(
    client: httpx.AsyncClient, master_prompt: MasterPrompt, tmp_path: Path
) -> None:
    respx.post(IMAGES_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(ImageGenerationError, match="unexpected /images/edits response shape"):
        await generate_image(
            valid_card_dict(),
            _ROLL,
            client=client,
            master_prompt=master_prompt,
            template_dir=_template_dir(tmp_path),
            prompt="PROMPT",
        )


def test_background_to_alpha_keys_exterior_but_spares_enclosed_white() -> None:
    out = background_to_alpha(make_white_bordered_png(width=40, height=60))
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    alpha = img.getchannel("A")

    # Every corner of the flat white exterior becomes fully transparent.
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((39, 0)) == 0
    assert alpha.getpixel((0, 59)) == 0
    assert alpha.getpixel((39, 59)) == 0
    # The dark card body stays opaque.
    assert alpha.getpixel((8, 50)) == 255
    # A white patch *enclosed* by the card is not connected to the corners,
    # so it must survive — this is why clouds/text inside the card are safe.
    assert alpha.getpixel((20, 30)) == 255


def test_background_to_alpha_rejects_a_leak() -> None:
    # A fully uniform image has no enclosing frame: the fill floods everything,
    # which must be rejected rather than returned as a blank transparent card.
    uniform = tiny_png()  # 4x4, single colour
    with pytest.raises(ImageGenerationError, match="leaked into the card"):
        background_to_alpha(uniform)


def test_background_to_alpha_rejects_undecodable_bytes() -> None:
    with pytest.raises(ImageGenerationError, match="could not open rendered image"):
        background_to_alpha(b"not a png")
