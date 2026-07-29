"""Tests for the versioned master-prompt loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.prompt import load_master_prompt


def test_master_prompt_loads_and_is_versioned() -> None:
    prompt = load_master_prompt()
    assert prompt.version == "v1"
    assert prompt.version_number == 1


def test_master_prompt_contains_the_load_bearing_instructions() -> None:
    text = load_master_prompt().text
    assert "MASTER PROMPT" in text
    assert "FULLY" in text and "TRANSPARENT" in text  # the alpha requirement
    assert "COMMON" in text and "MYTHIC" in text  # the rarity ladder
    assert "PIXEL ART" in text


def test_unversioned_prompt_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "master_prompt.md"
    bad.write_text("A prompt with no version marker at all.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="version marker"):
        load_master_prompt(bad)
