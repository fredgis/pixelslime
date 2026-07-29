"""Drift tests: the Pydantic ``Card`` must stay in lock-step with the contract."""

from __future__ import annotations

import json
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.ai.config import contracts_dir
from app.ai.models import Card, CardTypeName, RarityName


def _schema() -> dict[str, Any]:
    return json.loads((contracts_dir() / "card.schema.json").read_text(encoding="utf-8"))


def test_rarity_literal_matches_contract_enum() -> None:
    assert list(get_args(RarityName)) == _schema()["properties"]["rarity"]["enum"]


def test_type_literal_matches_contract_enum() -> None:
    assert list(get_args(CardTypeName)) == _schema()["properties"]["type"]["enum"]


def test_text_length_limits_match_contract() -> None:
    props = _schema()["properties"]
    model = Card.model_json_schema(by_alias=True)["properties"]
    for field in ("name", "personality", "power_name", "power_desc", "quote"):
        assert model[field]["maxLength"] == props[field]["maxLength"], field
        assert model[field]["minLength"] == props[field]["minLength"], field


def test_numeric_ranges_match_contract() -> None:
    props = _schema()["properties"]
    model = Card.model_json_schema(by_alias=True)["properties"]
    for field in (
        "serial",
        "level",
        "height_mm",
        "weight_g",
        "strength",
        "endurance",
        "agility",
        "happiness",
        "art_id",
        "style_id",
        "frame_id",
        "background_id",
        "biome_id",
        "mood_id",
        "mint_day",
    ):
        assert model[field]["minimum"] == props[field]["minimum"], field
        assert model[field]["maximum"] == props[field]["maximum"], field


def test_mochibo_contract_card_round_trips() -> None:
    path = contracts_dir() / "cards" / "mochibo.json"
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    card = Card.model_validate(raw)
    assert card.card_type == raw["type"]  # alias round-trips the 'type' key
    dumped = card.model_dump(by_alias=True, exclude_none=True)
    assert dumped["type"] == raw["type"]
    assert "card_type" not in dumped


def test_extra_keys_are_forbidden() -> None:
    path = contracts_dir() / "cards" / "mochibo.json"
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw["unexpected"] = 1
    with pytest.raises(ValidationError):
        Card.model_validate(raw)
