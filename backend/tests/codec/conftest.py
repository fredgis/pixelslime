"""Pytest bootstrap for the codec test package.

Puts the backend root on ``sys.path`` so ``import app.codec`` resolves regardless
of how pytest is invoked, and this directory too so the flat ``_helpers`` module
can be imported by the test modules beside it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]  # backend/
_TESTDIR = _HERE.parent  # backend/tests/codec/

for _p in (str(_BACKEND), str(_TESTDIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
