"""Loader for the versioned image master prompt (``docs/PLAN.md`` §5.1).

The prompt is stored as a flat ``.md`` file lifted verbatim from the plan so it
can be diffed and reviewed on its own. Its version id (``v1``) is parsed from the
header line and logged with every card, so a style drift six months from now can
still be traced back to the exact prompt that produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_MASTER_PROMPT_PATH = _PROMPTS_DIR / "master_prompt.md"
_VERSION_RE = re.compile(r"\(v(\d+)\)")


@dataclass(frozen=True, slots=True)
class MasterPrompt:
    """The master prompt text plus the version id parsed from its header."""

    text: str
    version: str

    @property
    def version_number(self) -> int:
        """Numeric form of the version, e.g. ``1`` for ``v1``."""
        return int(self.version.removeprefix("v"))


@lru_cache(maxsize=1)
def load_master_prompt(path: Path | None = None) -> MasterPrompt:
    """Read and parse the master prompt.

    Raises ``ValueError`` if the file has no ``(vN)`` version marker — we refuse
    to run an *unversioned* prompt rather than log a card we cannot later explain.
    """
    source = path or _MASTER_PROMPT_PATH
    text = source.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text.splitlines()[0] if text else "")
    if match is None:
        raise ValueError(
            f"master prompt at {source} is missing a '(vN)' version marker in its first line"
        )
    return MasterPrompt(text=text, version=f"v{match.group(1)}")
