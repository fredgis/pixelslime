"""Make the jobs package importable for the required repo-root pytest command."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
_TESTDIR = _HERE.parent

for _path in (str(_BACKEND), str(_TESTDIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
