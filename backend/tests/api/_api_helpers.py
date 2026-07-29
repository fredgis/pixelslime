"""Shared helpers for the API test package (uniquely named to avoid collisions).

Kept separate from ``conftest`` and given a package-unique name so a full-suite
run (which also loads the codec/ai ``_helpers`` modules) never imports the wrong
one. Puts ``backend/`` on ``sys.path`` at import so ``import app.*`` resolves.
"""

from __future__ import annotations

import random
import string
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_TESTDIR = _HERE.parent  # backend/tests/api/
_REPO_ROOT = _BACKEND.parent

for _p in (str(_BACKEND), str(_TESTDIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.codec import Card  # noqa: E402
from app.core.time import MINT_EPOCH, paris_today  # noqa: E402

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.core.source import InMemoryCardSource
    from app.storage.blob import InMemoryBlobStore

CONTRACTS_CARDS = _REPO_ROOT / "contracts" / "cards"
OPENAPI_PATH = _REPO_ROOT / "contracts" / "openapi.yaml"

ClientFactory = Callable[..., "tuple[TestClient, InMemoryCardSource, InMemoryBlobStore]"]


def load_fixture_card(name: str = "mochibo") -> Card:
    """Load a card straight from ``contracts/cards``."""
    return Card.model_validate_json((CONTRACTS_CARDS / f"{name}.json").read_text(encoding="utf-8"))


_MOCHIBO_DUMP = load_fixture_card("mochibo").model_dump()


def today_offset() -> int:
    """The ``mint_day`` value that maps onto today in Europe/Paris."""
    return (paris_today() - MINT_EPOCH).days


def build_card(
    serial: int,
    *,
    mint_day: int = 208,
    name: str = "Mochibo",
    type_: str = "FAIRY",
    rarity: str = "EPIC",
    happiness: int = 95,
    shiny: bool = False,
) -> Card:
    """Build a valid card from the mochibo template with the given overrides."""
    data = dict(_MOCHIBO_DUMP)
    data.update(
        serial=serial,
        mint_day=mint_day,
        name=name,
        type=type_,
        rarity=rarity,
        happiness=happiness,
        shiny=shiny,
    )
    return Card.model_validate(data)


def card_minted_today(serial: int = 1, **overrides: object) -> Card:
    """A card whose mint date is today, for the ``/api/cards/today`` path."""
    return build_card(serial, mint_day=today_offset(), **overrides)  # type: ignore[arg-type]


def build_multi_row_card(serial: int = 4242) -> Card:
    """Build a card whose PSC-1 stream spans more than one asmDB row.

    The free-text fields are filled with high-entropy content so DEFLATE (even with
    the pinned dictionary) cannot pack the body under a single 140-byte row. This is
    what lets a test drop a genuine *continuation* row to simulate a partial write.
    Deterministic, so the resulting row count is stable.
    """
    rng = random.Random(0xB1005)  # fixed seed → deterministic row count
    alphabet = string.ascii_letters + string.digits

    def noise(length: int) -> str:
        return "".join(rng.choice(alphabet) for _ in range(length))

    data = dict(_MOCHIBO_DUMP)
    data.update(
        serial=serial,
        name=noise(18),
        personality=noise(90),
        power_name=noise(20),
        power_desc=noise(90),
        quote=noise(40),
    )
    return Card.model_validate(data)
