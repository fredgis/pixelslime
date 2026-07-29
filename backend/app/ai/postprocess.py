"""Step 5 of the pipeline: post-processing (Pillow, offline).

From the verified 1024x1536 card PNG this produces the derived artefacts the rest
of the system needs:

* the alpha-trimmed PNG (transparent margin removed);
* a 512x768 WebP thumbnail (exactly half the card, so the layout is preserved);
* the SHA-256 of the canonical PNG — the codec anchors a card to its blob using
  the first 4 bytes (``art_sha``, ``docs/CODEC.md`` / ``card.schema.json``);
* the dominant palette, so the UI can tint itself from the art.

The SHA-256 is taken over the *exact bytes passed in* (the canonical card the
pipeline returns and W8 uploads), so ``art_sha`` provably identifies that blob.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from PIL import Image

from .config import THUMB_HEIGHT, THUMB_WIDTH
from .errors import PostProcessError

_ALPHA_OPAQUE_MIN = 128


@dataclass(frozen=True, slots=True)
class PostProcessResult:
    """Derived artefacts for one card."""

    sha256: str
    art_sha: str
    trimmed_png: bytes
    thumbnail_webp: bytes
    palette: list[str]


def _open(png_bytes: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
    except Exception as exc:
        raise PostProcessError(f"could not open image for post-processing: {exc}") from exc
    return img.convert("RGBA")


def trim_alpha(img: Image.Image) -> Image.Image:
    """Crop away the fully-transparent margin, by the alpha channel only.

    We trim on alpha (not ``Image.getbbox``, which keeps a transparent-but-
    coloured pixel) so a stray non-black-but-invisible pixel cannot defeat the
    trim.
    """
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        return img
    return img.crop(bbox)


def make_thumbnail(img: Image.Image) -> bytes:
    """Render the 512x768 WebP thumbnail from the full card canvas."""
    thumb = img.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="WEBP", quality=90, method=6)
    return buf.getvalue()


def dominant_palette(img: Image.Image, *, n_colors: int = 6) -> list[str]:
    """Return up to ``n_colors`` dominant hex colours of the opaque artwork.

    Fully/near transparent pixels are excluded so the card's transparent margin
    does not contribute a phantom colour.
    """
    work = img.convert("RGBA")
    work.thumbnail((96, 144), Image.Resampling.LANCZOS)
    pixels = cast("Sequence[tuple[int, int, int, int]]", work.get_flattened_data())
    opaque = [px[:3] for px in pixels if px[3] >= _ALPHA_OPAQUE_MIN]
    if not opaque:
        return []
    strip = Image.new("RGB", (len(opaque), 1))
    strip.putdata(opaque)
    quantized = strip.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
    palette = cast("list[int]", quantized.getpalette() or [])
    counts = cast("list[tuple[int, int]]", quantized.getcolors() or [])
    ordered = sorted(counts, reverse=True)  # (count, palette_index), most used first
    result: list[str] = []
    for _count, index in ordered:
        r, g, b = palette[index * 3 : index * 3 + 3]
        result.append(f"#{r:02X}{g:02X}{b:02X}")
    return result[:n_colors]


def postprocess(png_bytes: bytes, *, n_colors: int = 6) -> PostProcessResult:
    """Run every post-processing step and return the derived artefacts."""
    digest = hashlib.sha256(png_bytes).hexdigest()
    img = _open(png_bytes)

    trimmed = trim_alpha(img)
    trimmed_buf = io.BytesIO()
    trimmed.save(trimmed_buf, format="PNG")

    return PostProcessResult(
        sha256=digest,
        art_sha=digest[:8],
        trimmed_png=trimmed_buf.getvalue(),
        thumbnail_webp=make_thumbnail(img),
        palette=dominant_palette(img, n_colors=n_colors),
    )
