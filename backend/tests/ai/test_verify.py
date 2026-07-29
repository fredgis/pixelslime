"""Tests for verification: Pillow technical checks, similarity guard and vision."""

from __future__ import annotations

import io

import httpx
import respx
from _ai_helpers import chat_response, make_card_png, valid_card_dict, vision_payload
from conftest import CHAT_URL
from PIL import Image

from app.ai.verify import (
    average_hash,
    check_similarity,
    check_technical,
    check_vision,
    hash_agreement,
    verify_card,
)


def _img(png: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(png))
    im.load()
    return im


def test_technical_pass_on_well_formed_card() -> None:
    report = check_technical(make_card_png(seed=1))
    assert report.ok
    assert (report.width, report.height) == (1024, 1536)
    assert report.has_alpha
    assert report.corners_transparent
    assert report.is_portrait


def test_technical_rejects_opaque_background() -> None:
    report = check_technical(make_card_png(opaque=True))
    assert not report.ok
    assert report.has_alpha  # it HAS alpha...
    assert not report.corners_transparent  # ...but the corners are painted solid
    assert any("corners are not transparent" in f for f in report.failures)


def test_technical_rejects_missing_alpha_channel() -> None:
    report = check_technical(make_card_png(with_alpha=False))
    assert not report.ok
    assert not report.has_alpha
    assert any("no alpha channel" in f for f in report.failures)


def test_technical_rejects_wrong_dimensions() -> None:
    report = check_technical(make_card_png(width=512, height=768))
    assert not report.ok
    assert any("dimensions are 512x768" in f for f in report.failures)


def test_technical_rejects_landscape() -> None:
    report = check_technical(make_card_png(width=1536, height=1024))
    assert not report.ok
    assert not report.is_portrait
    assert any("not portrait" in f for f in report.failures)


def test_hash_agreement_is_one_for_identical() -> None:
    img = _img(make_card_png(seed=3))
    h = average_hash(img)
    assert hash_agreement(h, h) == 1.0


def test_similarity_high_for_same_art_low_for_different() -> None:
    a = make_card_png(seed=7)
    b = make_card_png(seed=7)
    c = make_card_png(seed=8)
    assert check_similarity(a, b) == 1.0
    assert check_similarity(a, c) < 0.82  # distinct art window -> below the guard


@respx.mock
async def test_vision_reports_match(client: httpx.AsyncClient) -> None:
    card = valid_card_dict()
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(vision_payload(card)))
    )
    report = await check_vision(make_card_png(), card, client=client)
    assert report.matches
    assert not report.mismatches
    assert not report.too_similar_to_reference


@respx.mock
async def test_vision_detects_stat_mismatch(client: httpx.AsyncClient) -> None:
    card = valid_card_dict()
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(vision_payload(card, printed_level=99)))
    )
    report = await check_vision(make_card_png(), card, client=client)
    assert not report.matches
    assert any("level" in m for m in report.mismatches)


@respx.mock
async def test_vision_flags_too_similar_on_two_signals(client: httpx.AsyncClient) -> None:
    card = valid_card_dict()
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json=chat_response(
                vision_payload(card, is_pink_dome_slime=True, scene_is_cozy_reading_room=True)
            ),
        )
    )
    report = await check_vision(make_card_png(), card, client=client)
    assert report.too_similar_to_reference


@respx.mock
async def test_verify_card_ok_when_all_checks_pass(client: httpx.AsyncClient) -> None:
    card = valid_card_dict()
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(vision_payload(card)))
    )
    result = await verify_card(
        make_card_png(seed=1),
        card,
        client=client,
        reference_bytes=make_card_png(seed=2),
    )
    assert result.ok
    assert result.reasons == []
    assert result.vision is not None


async def test_verify_card_flags_technical_and_similarity_without_vision() -> None:
    card = valid_card_dict()
    png = make_card_png(opaque=True, seed=4)
    result = await verify_card(
        png,
        card,
        client=None,  # type: ignore[arg-type]  # run_vision=False never touches the client
        reference_bytes=png,  # identical -> similarity 1.0
        run_vision=False,
    )
    assert not result.ok
    assert any("corners are not transparent" in r for r in result.reasons)
    assert any("too similar to the reference" in r for r in result.reasons)
    assert result.vision is None
