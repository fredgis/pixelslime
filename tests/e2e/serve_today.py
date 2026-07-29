"""Supplementary E2E backend: the real app, seeded from contracts/cards *plus* one
synthetic card dated **today**.

This is deliberately NOT the canonical harness backend. The canonical run is
``uvicorn app.main:app`` with ``FAKE_BACKEND=1``, seeded only from
``contracts/cards/*.json``. W10 owns ``tests/e2e/`` only; this module imports the
real backend and uses its public ``create_app(source=..., blob=...)`` injection
seam. It does **not** modify any W6/W7 code.

Why it exists: with only the three contract seed cards and the run-date clock,
``/api/cards/today`` returns 404 (none of the seeds blooms today), so the flagship
reveal ceremony and the "stats match ``/api/cards/today``" assertion cannot run
against the pure seed. Seeding one extra card whose mint date is *today* lets the
harness exercise those mechanics against the real serialization path — and, as a
bonus, demonstrate the top-level ``dayNumber`` divergence live.

Run with::

    FAKE_BACKEND=1 uvicorn serve_today:app
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.codec import Card  # noqa: E402
from app.core.config import load_settings  # noqa: E402
from app.core.time import MINT_EPOCH, paris_today  # noqa: E402
from app.main import _placeholder_pair, build_fakes, create_app  # noqa: E402

#: A free serial not used by any contract seed (1, 900, 65535).
_SYNTHETIC_TODAY_SERIAL = 2


def _today_card() -> Card:
    """Build a valid card whose mint date is today, cloned from the Mochibo seed.

    Cloning a real contract card guarantees a schema-valid, codec-encodable payload;
    only the serial, name and mint day are changed so it lands on today's bloom slot.
    """
    mint_day = (paris_today() - MINT_EPOCH).days
    raw = json.loads((_REPO_ROOT / "contracts" / "cards" / "mochibo.json").read_text("utf-8"))
    raw.update(serial=_SYNTHETIC_TODAY_SERIAL, name="Todaybloom", mint_day=mint_day)
    return Card.model_validate(raw)


def _build_app():  # noqa: ANN202 - FastAPI app, imported lazily by uvicorn
    source, blob = build_fakes()
    card = _today_card()
    source.add_card(card)
    png, webp = _placeholder_pair(card)
    blob.seed_card(card.serial, png, webp)
    return create_app(load_settings(), source=source, blob=blob)


app = _build_app()
