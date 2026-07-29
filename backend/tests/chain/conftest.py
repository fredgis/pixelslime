"""Pytest bootstrap for the chain test package.

Mirrors the other test packages: puts the backend root on ``sys.path`` so
``import app.chain`` resolves however pytest is invoked, and this directory too so
the flat ``_chain_helpers`` module imports cleanly from the tests beside it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_TESTDIR = _HERE.parent  # backend/tests/chain/

for _p in (str(_BACKEND), str(_TESTDIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
