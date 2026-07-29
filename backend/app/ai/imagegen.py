"""Step 3 of the pipeline: the image — gpt-image-2 via ``/images/edits``.

``docs/PLAN.md`` §1.1/§5.2: ``/generations`` rejects reference images, so we use the
multipart ``/images/edits`` endpoint and pass references under the **plural**
``image[]`` field. ``mochibo.png`` — the anatomy canon — is sent on *every* call so
all cards share one layout; a per-rarity exemplar ``ref-<rarity>.png`` is added as
a second ``image[]`` once one exists, and we degrade gracefully to the single
reference until then.

The prompt pins the *finish* for the rolled rarity in words (the reference only
pins the anatomy), which is what keeps a COMMON from inheriting Mochibo's EPIC
gold frame — the central risk R12 in the plan.

Transparency is *not* produced by the model: gpt-image-2 on ``/images/edits``
cannot emit alpha (``config.IMAGE_BACKGROUND``). The prompt therefore asks for a
flat white exterior and :func:`background_to_alpha` keys that white to real alpha
in Pillow, so the card still satisfies the hard transparency rule.
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw

from .config import (
    CARD_HEIGHT,
    CARD_SIZE,
    CARD_WIDTH,
    IMAGE_BACKGROUND,
    IMAGE_BG_KEY_MAX_FRACTION,
    IMAGE_BG_KEY_THRESHOLD,
    IMAGE_MODEL,
    IMAGE_OUTPUT_FORMAT,
    IMAGE_QUALITY,
    RARITY_FINISHES,
    RARITY_ORDER,
    assets_template_dir,
    rarity_ordinal,
)
from .errors import ImageGenerationError, RateLimitError
from .prompt import MasterPrompt
from .roll import Roll

#: HTTP statuses worth retrying — transient throttling / server hiccups.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 5
_BACKOFF_BASE = 2.0
_BACKOFF_CAP = 60.0
#: The four canvas corners, seeds for the exterior flood-fill.
_CORNERS = ((0, 0), (-1, 0), (0, -1), (-1, -1))

Sleeper = Callable[[float], Awaitable[None]]


def resolve_references(rarity: str, *, template_dir: Path | None = None) -> list[Path]:
    """Return the reference images to attach, canon first.

    The first element is always ``mochibo.png``; a tier exemplar is appended only
    if a *distinct* ``ref-<rarity>.png`` file exists. Sending Mochibo twice (its
    own path == the EPIC exemplar path) is avoided — the singular anatomy canon
    already serves the EPIC tier.
    """
    directory = template_dir or assets_template_dir()
    canon = directory / "mochibo.png"
    if not canon.is_file():
        raise ImageGenerationError(f"anatomy canon not found at {canon}")
    references = [canon]
    exemplar = directory / f"ref-{rarity.lower()}.png"
    if exemplar.is_file() and exemplar.resolve() != canon.resolve():
        references.append(exemplar)
    return references


def promote_exemplar(
    rarity: str,
    png_bytes: bytes,
    *,
    template_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Install ``png_bytes`` as the tier exemplar ``ref-<rarity>.png`` (human-run).

    §5.2's two-reference strategy is meant to be self-populating: once a card is
    judged the canonical look of its tier it becomes that tier's exemplar, and
    :func:`resolve_references` then attaches it as the second ``image[]`` on every
    later generation of the same rarity. Deciding *which* card earns that is a
    taste judgement, so promotion is a deliberate, human-invoked step — never
    something the daily job does unattended (see the W4 follow-up report). The
    bytes are validated (portrait ``1024x1536`` with a real alpha channel) so a
    malformed or opaque render cannot silently become the canon, and an existing
    exemplar is left untouched unless ``overwrite`` is set.
    """
    if rarity.upper() not in RARITY_ORDER:
        raise ImageGenerationError(f"unknown rarity {rarity!r}; cannot name an exemplar for it")
    directory = template_dir or assets_template_dir()
    target = directory / f"ref-{rarity.lower()}.png"
    if target.exists() and not overwrite:
        raise ImageGenerationError(
            f"exemplar {target.name} already exists; pass overwrite=True to replace it"
        )
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
    except Exception as exc:
        raise ImageGenerationError(f"exemplar is not a decodable image: {exc}") from exc
    if img.size != (CARD_WIDTH, CARD_HEIGHT):
        raise ImageGenerationError(
            f"exemplar must be {CARD_WIDTH}x{CARD_HEIGHT} portrait, got {img.width}x{img.height}"
        )
    if "A" not in img.getbands():
        raise ImageGenerationError("exemplar has no alpha channel; expected a transparent card")
    directory.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png_bytes)
    return target


def _finish_contrast(rarity: str) -> str:
    ordinal = rarity_ordinal(rarity)
    epic = rarity_ordinal("EPIC")
    if ordinal < epic:
        return (
            "This is a LOWER tier than EPIC, so the card must look visibly LESS "
            "ornate than an EPIC card: no gold, no crown gem, no heavy foil, no "
            "dense sparkle."
        )
    if ordinal == epic:
        return "This is the EPIC tier."
    return (
        "This is a HIGHER tier than EPIC, so the card must look visibly MORE "
        "exceptional, radiant and richly finished than an EPIC card."
    )


def build_image_prompt(master_prompt: MasterPrompt, card: Mapping[str, Any], roll: Roll) -> str:
    """Compose the full image prompt: master brief + concrete values + finish.

    Every printed number and word is stated verbatim so the model paints exactly
    the JSON the database will store, and the reference's role (layout only, not
    the creature or scene) and the rolled rarity's finish are spelled out.
    """
    rarity = str(card["rarity"])
    card_id = f"{card['series']}-{int(card['serial']):04d}"
    height_m = int(card["height_mm"]) / 1000
    weight_kg = int(card["weight_g"]) / 1000
    companion = roll.companion if roll.has_companion else "no companion"
    accessory = roll.accessory if roll.has_accessory else "no accessory"
    shiny = "yes — add a subtle sparkling shiny sheen" if roll.shiny else "no"

    return (
        f"{master_prompt.text}\n\n"
        "════════════════════════════════════════════════════════════\n"
        "CONCRETE VALUES FOR THIS EXACT CARD — print them verbatim on the card, "
        "do not invent or change any number or word:\n"
        f"  ID:          {card_id}\n"
        f"  NAME:        {card['name']}\n"
        f"  TYPE:        {card['type']}\n"
        f"  LEVEL:       {card['level']}\n"
        f"  RARITY:      {rarity}\n"
        f"  HEIGHT:      {height_m:.2f} m\n"
        f"  WEIGHT:      {weight_kg:.2f} kg\n"
        f"  PERSONALITY: {card['personality']}\n"
        f"  POWER:       {card['power_name']} — {card['power_desc']}\n"
        f"  STRENGTH:    {card['strength']}\n"
        f"  ENDURANCE:   {card['endurance']}\n"
        f"  AGILITY:     {card['agility']}\n"
        f"  HAPPINESS:   {card['happiness']}\n"
        f'  QUOTE:       "{card["quote"]}"\n\n'
        "SCENE & CREATURE — random, and it must NOT copy the reference:\n"
        f"  - Scene / biome: {roll.biome}\n"
        f"  - Mood: {roll.mood}\n"
        f"  - Companion: {companion}\n"
        f"  - Accessory: {accessory}\n"
        f"  - Shiny: {shiny}\n\n"
        "REFERENCE IMAGES — READ CAREFULLY:\n"
        "  - The attached reference image(s) define ONLY the CARD STYLE and "
        "LAYOUT (proportions, rounded border, title bar, type pill, rarity badge "
        "position, art window, height/weight strip, personality+power block, the "
        "four stat bars, the quote bubble, the ID footer).\n"
        "  - They do NOT define the creature and do NOT define the scene. Invent a "
        "NEW, DIFFERENT slime and a NEW scene. Do not reproduce the reference's "
        "pink dome slime, its cosy reading room, or its cat.\n\n"
        f"RARITY FINISH — this card is {rarity}. Its finish MUST be: "
        f"{RARITY_FINISHES[rarity]} {_finish_contrast(rarity)}\n"
        "The card anatomy is identical across rarities; only this finish changes.\n\n"
        "RENDERING NOTE — this overrides the transparency line in the brief above: "
        "the renderer cannot output alpha, so do NOT leave the outside transparent "
        "and do NOT paint scenery, a gradient, a drop shadow or a checkerboard there. "
        "Instead fill the entire area OUTSIDE the rounded card border with a single "
        "FLAT, SOLID, UNIFORM WHITE — the pipeline keys that white to real "
        "transparency afterwards. Keep a small, even white margin around the whole card."
    )


def build_request(
    prompt: str, references: Sequence[Path], *, n: int = 1
) -> tuple[dict[str, str], list[tuple[str, tuple[str, bytes, str]]]]:
    """Build the multipart ``(data, files)`` for ``/images/edits``.

    Returned separately from the HTTP call so the exact shape — the plural
    ``image[]`` field and the ever-present canon — can be asserted in a unit test
    without a network round-trip.
    """
    files: list[tuple[str, tuple[str, bytes, str]]] = [
        ("image[]", (path.name, path.read_bytes(), "image/png")) for path in references
    ]
    data = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "size": CARD_SIZE,
        "background": IMAGE_BACKGROUND,
        "output_format": IMAGE_OUTPUT_FORMAT,
        "quality": IMAGE_QUALITY,
        "n": str(n),
    }
    return data, files


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    value: str | None = resp.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date form: fall back to exponential backoff


def _backoff_seconds(attempt: int) -> float:
    return min(_BACKOFF_CAP, _BACKOFF_BASE * (2.0**attempt))


def _decode_image(resp: httpx.Response) -> bytes:
    data: Any = resp.json()
    try:
        items = data["data"]
        b64 = items[0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageGenerationError(f"unexpected /images/edits response shape: {exc}") from exc
    if not isinstance(b64, str) or not b64:
        raise ImageGenerationError("response contained no b64_json image data")
    try:
        return base64.b64decode(b64)
    except (ValueError, TypeError) as exc:
        raise ImageGenerationError(f"b64_json was not valid base64: {exc}") from exc


def background_to_alpha(
    png_bytes: bytes,
    *,
    threshold: int = IMAGE_BG_KEY_THRESHOLD,
    max_fraction: float = IMAGE_BG_KEY_MAX_FRACTION,
) -> bytes:
    """Key the flat exterior of a rendered card to real transparency.

    gpt-image-2 renders the area outside the card as an opaque flat fill (we ask
    for white) because it cannot emit alpha on ``/images/edits``. This flood-fills
    from each of the four corners — seeding from the corner's own colour, so it
    adapts to whatever uniform fill the model used — and turns that connected
    exterior region transparent. Because the fill only follows *connected* pixels,
    whites *inside* the card (clouds, text) are protected by the darker frame that
    encloses them.

    Raises :class:`ImageGenerationError` if the fill removes more than
    ``max_fraction`` of the canvas, which means it leaked past the border into the
    card rather than clearing a thin exterior margin.
    """
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception as exc:
        raise ImageGenerationError(f"could not open rendered image for keying: {exc}") from exc

    width, height = img.size
    for dx, dy in _CORNERS:
        seed = (dx % width, dy % height)
        ImageDraw.floodfill(img, seed, (0, 0, 0, 0), thresh=threshold)

    keyed = img.getchannel("A").histogram()[0]
    fraction = keyed / (width * height)
    if fraction > max_fraction:
        raise ImageGenerationError(
            f"background keying removed {fraction:.0%} of the image (> {max_fraction:.0%}); "
            "the flat fill likely leaked into the card"
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_image(
    card: Mapping[str, Any],
    roll: Roll,
    *,
    client: httpx.AsyncClient,
    master_prompt: MasterPrompt,
    template_dir: Path | None = None,
    prompt: str | None = None,
    n: int = 1,
    max_attempts: int = _MAX_ATTEMPTS,
    recover_alpha: bool = True,
    sleep: Sleeper = asyncio.sleep,
) -> bytes:
    """Generate the card PNG, retrying transient failures with backoff.

    A 429 or 5xx is retried, honouring a ``Retry-After`` header when present and
    otherwise backing off exponentially; a non-retryable 4xx is raised at once so
    a genuinely bad request is not hammered. ``sleep`` is injectable so tests
    exercise the backoff without waiting. ``prompt`` may be supplied pre-built so
    the caller can log the exact text sent; otherwise it is composed here.

    When ``recover_alpha`` is set (the default), the opaque render is passed
    through :func:`background_to_alpha` so the returned PNG has a real transparent
    exterior — the model itself cannot emit alpha on ``/images/edits``.
    """
    references = resolve_references(str(card["rarity"]), template_dir=template_dir)
    if prompt is None:
        prompt = build_image_prompt(master_prompt, card, roll)
    data, files = build_request(prompt, references, n=n)

    last_detail = ""
    last_status: int | None = None
    last_retry_after: float | None = None
    for attempt in range(max_attempts):
        wait: float
        try:
            resp = await client.post("images/edits", data=data, files=files)
        except httpx.HTTPError as exc:
            last_detail = f"transport error: {exc}"
            last_status = None
            wait = _backoff_seconds(attempt)
        else:
            if resp.status_code == 200:
                png = _decode_image(resp)
                return background_to_alpha(png) if recover_alpha else png
            last_detail = f"HTTP {resp.status_code}: {resp.text[:300]}"
            last_status = resp.status_code
            if resp.status_code not in _RETRYABLE_STATUS:
                raise ImageGenerationError(f"/images/edits failed, not retryable — {last_detail}")
            retry_after = _retry_after_seconds(resp)
            last_retry_after = retry_after
            wait = retry_after if retry_after is not None else _backoff_seconds(attempt)

        if attempt + 1 >= max_attempts:
            break
        await sleep(wait)

    if last_status == 429:
        # A persistent 429 gets its own typed error carrying the parsed Retry-After
        # and the attempts spent, so W8 can react to structured data rather than
        # string-matching. The message keeps the "HTTP 429" marker for callers that
        # have not yet migrated off substring matching.
        raise RateLimitError(
            f"/images/edits rate-limited (HTTP 429) after {max_attempts} attempts — "
            f"last: {last_detail}",
            retry_after=last_retry_after,
            attempts=max_attempts,
        )
    raise ImageGenerationError(
        f"/images/edits failed after {max_attempts} attempts — last: {last_detail}"
    )
