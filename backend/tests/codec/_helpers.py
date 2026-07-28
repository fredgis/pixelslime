"""Shared fixtures and Hypothesis strategies for the codec tests.

The ``cards`` strategy generates cards that are valid against **both** the schema's
character limits and the codec's stricter UTF-8 byte limits (§3.6), so every card
it yields is guaranteed encodable and must round-trip. Text is drawn from the full
UTF-8 range (minus the four forbidden control bytes and surrogates) to exercise
multi-byte encoding, then trimmed to the byte budget.
"""

from __future__ import annotations

import json
from pathlib import Path

import hypothesis.strategies as st

from app.codec import RARITIES, TYPES, Card, Flags

_CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "cards"

FIXTURE_NAMES = ("mochibo", "worstcase-unseen", "worstcase-maxlen")


def load_card(name: str) -> Card:
    """Load a fixture card by stem name from ``contracts/cards``."""
    return Card.model_validate(
        json.loads((_CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))
    )


def load_raw(name: str) -> dict[str, object]:
    """Load the raw fixture JSON (with display-only fields still present)."""
    return json.loads((_CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))


def _fit_bytes(text: str, byte_max: int) -> str:
    """Trim trailing characters until the UTF-8 encoding fits ``byte_max`` bytes."""
    while len(text.encode("utf-8")) > byte_max:
        text = text[:-1]
    return text


def text_field(char_max: int, byte_max: int) -> st.SearchStrategy[str]:
    """A non-empty string within both a character and a UTF-8 byte limit."""
    alphabet = st.characters(codec="utf-8", min_codepoint=1, exclude_characters="\x1f\r\n")
    return (
        st.text(alphabet=alphabet, min_size=1, max_size=char_max)
        .map(lambda s: _fit_bytes(s, byte_max))
        .filter(lambda s: len(s) >= 1)
    )


@st.composite
def cards(draw: st.DrawFn) -> Card:
    """Generate a schema- and byte-limit-valid :class:`Card`."""
    return Card(
        serial=draw(st.integers(min_value=1, max_value=65535)),
        name=draw(text_field(18, 36)),
        level=draw(st.integers(min_value=1, max_value=100)),
        rarity=draw(st.sampled_from(RARITIES)),
        type=draw(st.sampled_from(TYPES)),
        height_mm=draw(st.integers(min_value=1, max_value=65535)),
        weight_g=draw(st.integers(min_value=1, max_value=65535)),
        strength=draw(st.integers(min_value=0, max_value=100)),
        endurance=draw(st.integers(min_value=0, max_value=100)),
        agility=draw(st.integers(min_value=0, max_value=100)),
        happiness=draw(st.integers(min_value=0, max_value=100)),
        art_id=draw(st.integers(min_value=0, max_value=255)),
        style_id=draw(st.integers(min_value=0, max_value=255)),
        frame_id=draw(st.integers(min_value=0, max_value=255)),
        background_id=draw(st.integers(min_value=0, max_value=255)),
        biome_id=draw(st.integers(min_value=0, max_value=255)),
        mood_id=draw(st.integers(min_value=0, max_value=255)),
        personality=draw(text_field(90, 180)),
        power_name=draw(text_field(20, 40)),
        power_desc=draw(text_field(90, 180)),
        quote=draw(text_field(40, 80)),
        mint_day=draw(st.integers(min_value=0, max_value=65535)),
        shiny=draw(st.booleans()),
        flags=Flags(
            has_companion=draw(st.booleans()),
            has_accessory=draw(st.booleans()),
            verified=draw(st.booleans()),
            on_chain=draw(st.booleans()),
            seed=draw(st.booleans()),
        ),
        art_sha=draw(st.from_regex(r"[0-9a-f]{8}", fullmatch=True)),
    )
