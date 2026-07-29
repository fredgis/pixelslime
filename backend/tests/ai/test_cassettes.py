"""Offline replay of the recorded real calls.

``docs/PLAN.md`` §5 requires one real call of each kind, recorded to
``tests/ai/cassettes/`` and replayed offline. These tests feed the recorded
responses back through the real client code with ``respx`` so the parsing,
validation and comparison paths run against genuine server output — no network,
no cost, no rate limit. The image cassette is stored shape-only (its base64 is
truncated), so it is asserted structurally; the Pillow paths use synthetic PNGs.
"""

from __future__ import annotations

import base64

import httpx
import pytest
import respx
from _ai_helpers import cassette_exists, load_cassette, make_card_png, valid_card_dict
from conftest import CHAT_URL

from app.ai.metadata import generate_metadata
from app.ai.prompt import MasterPrompt
from app.ai.roll import roll
from app.ai.verify import check_vision

pytestmark = pytest.mark.skipif(
    not cassette_exists("metadata.chat.json"),
    reason="cassettes not recorded (run tests/ai/_record_and_run.py once with credentials)",
)


@respx.mock
async def test_metadata_cassette_replays_offline(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=load_cassette("metadata.chat.json"))
    )

    text = await generate_metadata(
        roll(200, forced_rarity="COMMON"),
        used_names=[],
        client=client,
        master_prompt=master_prompt,
    )

    # The recorded gpt-5.6-sol response parses cleanly and passes length checks.
    assert text.name == "Nimbusnooze"
    assert text.level == 14
    assert (text.strength, text.endurance, text.agility, text.happiness) == (22, 47, 31, 78)
    assert text.power_name == "Crane Constellation"
    assert text.quote == "Wake me when the stars twinkle."


@respx.mock
async def test_vision_cassette_replays_offline(client: httpx.AsyncClient) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=load_cassette("vision.chat.json"))
    )

    card = valid_card_dict(
        name="Nimbusnooze",
        level=14,
        rarity="COMMON",
        type="COSMIC",
        strength=22,
        endurance=47,
        agility=31,
        happiness=78,
    )
    report = await check_vision(make_card_png(), card, client=client)

    # The recorded readback agrees with the JSON on every printed field, and it
    # is not one of the Mochibo look-alike signals.
    assert report.matches
    assert report.mismatches == []
    assert not report.too_similar_to_reference


def test_image_cassette_has_the_expected_shape() -> None:
    env = load_cassette("images_edits.response.json")
    item = env["data"][0]
    assert item["_truncated"] is True
    assert item["_b64_json_full_len"] > 100_000  # the real PNG was ~2.3 MB of base64
    # The stored prefix is still valid base64 and starts with the PNG magic bytes.
    head = base64.b64decode(item["b64_json"] + "=" * (-len(item["b64_json"]) % 4))
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
