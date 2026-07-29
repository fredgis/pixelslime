"""Tests for the metadata step: schema request, length limits and the retry path."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from _ai_helpers import chat_response, metadata_payload
from conftest import CHAT_URL

from app.ai.config import TEXT_MODEL
from app.ai.errors import MetadataValidationError
from app.ai.metadata import generate_metadata
from app.ai.prompt import MasterPrompt
from app.ai.roll import roll

_ROLL = roll(200, forced_rarity="COMMON")


@respx.mock
async def test_valid_response_becomes_cardtext(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(metadata_payload()))
    )
    text = await generate_metadata(_ROLL, (), client=client, master_prompt=master_prompt)

    assert route.call_count == 1
    assert text.name == "Pebblory"
    assert text.level == 12
    assert text.happiness == 88

    body = json.loads(route.calls[0].request.content)
    assert body["model"] == TEXT_MODEL
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


@respx.mock
async def test_overlong_name_triggers_shorten_retry_then_succeeds(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    too_long = metadata_payload(name="Reginald-the-Magnificent-Slime")  # 30 chars > 18
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=chat_response(too_long)),
            httpx.Response(200, json=chat_response(metadata_payload())),
        ]
    )
    text = await generate_metadata(_ROLL, (), client=client, master_prompt=master_prompt)

    assert route.call_count == 2
    assert text.name == "Pebblory"
    # The correction turn must actually tell the model to shorten the field.
    correction = json.loads(route.calls[1].request.content)
    last_user = correction["messages"][-1]["content"]
    assert "shorten" in last_user.lower()
    assert "name" in last_user.lower()


@respx.mock
async def test_persistent_overlength_raises_after_retries_without_truncating(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    too_long = metadata_payload(personality="x" * 200)  # way over the 90-char limit
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(too_long))
    )
    with pytest.raises(MetadataValidationError) as excinfo:
        await generate_metadata(_ROLL, (), client=client, master_prompt=master_prompt)

    assert route.call_count == 3  # initial + 2 retries
    assert any("personality" in p for p in excinfo.value.problems)


@respx.mock
async def test_duplicate_name_is_rejected(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(metadata_payload(name="Pebblory")))
    )
    with pytest.raises(MetadataValidationError) as excinfo:
        await generate_metadata(
            _ROLL, ["pebblory"], client=client, master_prompt=master_prompt, max_retries=0
        )
    assert any("already used" in p for p in excinfo.value.problems)


@respx.mock
async def test_out_of_range_level_is_rejected(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(metadata_payload(level=200)))
    )
    with pytest.raises(MetadataValidationError) as excinfo:
        await generate_metadata(
            _ROLL, (), client=client, master_prompt=master_prompt, max_retries=0
        )
    assert any("level" in p and "between 1 and 100" in p for p in excinfo.value.problems)


@respx.mock
async def test_forbidden_newline_is_rejected(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=chat_response(metadata_payload(quote="hi\nthere")))
    )
    with pytest.raises(MetadataValidationError) as excinfo:
        await generate_metadata(
            _ROLL, (), client=client, master_prompt=master_prompt, max_retries=0
        )
    assert any("newline" in p for p in excinfo.value.problems)


@respx.mock
async def test_byte_limit_rejected_even_when_char_count_fits(
    client: httpx.AsyncClient, master_prompt: MasterPrompt
) -> None:
    # 13 cake emoji: 13 characters (<= 18) but 52 UTF-8 bytes (> 36-byte name limit).
    payload = metadata_payload(name="\U0001f370" * 13)
    respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_response(payload)))
    with pytest.raises(MetadataValidationError) as excinfo:
        await generate_metadata(
            _ROLL, (), client=client, master_prompt=master_prompt, max_retries=0
        )
    assert any("UTF-8 bytes" in p for p in excinfo.value.problems)
