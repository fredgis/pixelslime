"""Best-effort access to W0's ``contracts/design-tokens.json``.

The backend needs two display-only facts that live in the design tokens: the
**rarity house** names (``EPIC → "Aurora"``) and the per-type / per-rarity
**colours** used to seed a card's palette. Both are optional in
``contracts/openapi.yaml``, so this loader is deliberately forgiving: if the
tokens file cannot be found (e.g. an installed wheel without the repo tree), it
logs once and returns empty maps rather than failing a request. It never imports
another workstream's package, so there is no coupling to W2/W4.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from .logging import get_logger

_log = get_logger(__name__)


@lru_cache(maxsize=1)
def _repo_root() -> Path | None:
    """Walk up until ``contracts/design-tokens.json`` is found; ``None`` if absent."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "contracts" / "design-tokens.json").is_file():
            return parent
    return None


@lru_cache(maxsize=1)
def _design_tokens() -> dict[str, object]:
    root = _repo_root()
    if root is None:
        _log.warning("design_tokens_missing", detail="rarity houses and palette will be omitted")
        return {}
    path = root / "contracts" / "design-tokens.json"
    try:
        return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:  # pragma: no cover - unreadable/invalid tokens
        _log.warning("design_tokens_unreadable", error=str(exc))
        return {}


@lru_cache(maxsize=1)
def rarity_houses() -> dict[str, str]:
    """Return ``{RARITY: house}`` (e.g. ``EPIC → "Aurora"``); empty if unavailable."""
    tokens = _design_tokens()
    rarity = tokens.get("rarity")
    if not isinstance(rarity, dict):
        return {}
    houses: dict[str, str] = {}
    for name, entry in rarity.items():
        if isinstance(entry, dict) and isinstance(entry.get("house"), str):
            houses[name] = entry["house"]
    return houses


@lru_cache(maxsize=1)
def _rarity_colors() -> dict[str, str]:
    tokens = _design_tokens()
    rarity = tokens.get("rarity")
    if not isinstance(rarity, dict):
        return {}
    colors: dict[str, str] = {}
    for name, entry in rarity.items():
        if isinstance(entry, dict) and isinstance(entry.get("color"), str):
            colors[name] = entry["color"]
    return colors


@lru_cache(maxsize=1)
def _type_colors() -> dict[str, str]:
    tokens = _design_tokens()
    type_map = tokens.get("type")
    if not isinstance(type_map, dict):
        return {}
    return {name: value for name, value in type_map.items() if isinstance(value, str)}


def palette_for(slime_type: str, rarity: str) -> list[str]:
    """Return a small dominant-colour palette for a card, from type then rarity.

    The real artwork colours are not on the hot path (they would mean touching the
    PNG), so the UI is seeded with the type and rarity colours the design system
    already assigns. Returns ``[]`` when tokens are unavailable so the field is
    simply omitted rather than wrong.
    """
    palette: list[str] = []
    for color in (_type_colors().get(slime_type), _rarity_colors().get(rarity)):
        if color and color not in palette:
            palette.append(color)
    return palette


@lru_cache(maxsize=1)
def _lookups() -> dict[str, list[str]]:
    """Load ``contracts/lookups.json`` (biomes / moods / companions); empty if absent.

    The ids are frozen list indices (append-only), so resolving a name is a direct
    index. Like the design tokens this is deliberately forgiving: a missing or
    unreadable file degrades to empty maps and the labels are simply omitted rather
    than failing a request. This is W4's authoritative table; we never import W4.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "contracts" / "lookups.json"
        if candidate.is_file():
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:  # pragma: no cover - unreadable/invalid
                _log.warning("lookups_unreadable", error=str(exc))
                return {}
            tables: dict[str, list[str]] = {}
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(value, list) and all(isinstance(item, str) for item in value):
                        tables[key] = value
            return tables
    _log.warning("lookups_missing", detail="biome/mood/companion labels will be omitted")
    return {}


def _label(table: str, index: int) -> str | None:
    """Resolve a frozen-table label by id, or ``None`` if out of range / unavailable."""
    values = _lookups().get(table)
    if values is None or not 0 <= index < len(values):
        return None
    return values[index]


def biome_name(biome_id: int) -> str | None:
    """Display name for a ``biome_id`` (``lookups.biomes``), or ``None``."""
    return _label("biomes", biome_id)


def mood_name(mood_id: int) -> str | None:
    """Display name for a ``mood_id`` (``lookups.moods``), or ``None``."""
    return _label("moods", mood_id)


def companion_name(companion_id: int) -> str | None:
    """Display name for a ``companion_id`` (``lookups.companions``), or ``None``."""
    return _label("companions", companion_id)
