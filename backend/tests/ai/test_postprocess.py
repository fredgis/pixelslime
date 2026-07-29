"""Tests for post-processing: hash, alpha trim, thumbnail and palette."""

from __future__ import annotations

import io
import re

from _ai_helpers import make_card_png
from PIL import Image

from app.ai.postprocess import dominant_palette, postprocess

_HEX = re.compile(r"^#[0-9A-F]{6}$")


def _img(png: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(png))
    im.load()
    return im


def test_postprocess_produces_all_artifacts() -> None:
    png = make_card_png(seed=1)
    result = postprocess(png)

    assert re.fullmatch(r"[0-9a-f]{64}", result.sha256)
    assert result.art_sha == result.sha256[:8]

    thumb = _img(result.thumbnail_webp)
    assert thumb.size == (512, 768)

    assert result.palette
    assert all(_HEX.match(c) for c in result.palette)


def test_sha256_is_stable_and_content_addressed() -> None:
    png = make_card_png(seed=2)
    assert postprocess(png).sha256 == postprocess(png).sha256
    assert postprocess(make_card_png(seed=2)).sha256 != postprocess(make_card_png(seed=3)).sha256


def test_dominant_palette_ignores_transparent_pixels() -> None:
    blank = Image.new("RGBA", (64, 96), (0, 0, 0, 0))
    assert dominant_palette(blank) == []
