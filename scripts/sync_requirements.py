"""Keep backend/requirements.txt in step with pyproject.toml.

The Docker build installs from requirements.txt rather than parsing pyproject
inside the image, so the dependency layer is stable and cacheable and the build
does not depend on a heredoc or a TOML parser being available at that stage.

That only works if the two stay in step, so CI runs this with --check.

Usage:
    python scripts/sync_requirements.py           # rewrite the file
    python scripts/sync_requirements.py --check   # fail if it is stale
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "backend" / "pyproject.toml"
REQUIREMENTS = ROOT / "backend" / "requirements.txt"

HEADER = (
    "# Generated from pyproject.toml by scripts/sync_requirements.py - do not edit by hand.\n"
    "# Exists so the Docker build has a stable, cacheable dependency layer that does not\n"
    "# depend on parsing pyproject inside the image.\n"
)


def render() -> str:
    cfg = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = cfg["project"]
    deps = list(project["dependencies"])
    # The chain extra is needed at runtime: the daily job anchors on-chain.
    deps += list(project["optional-dependencies"]["chain"])
    return HEADER + "\n".join(sorted(deps)) + "\n"


def main() -> int:
    expected = render()
    if "--check" in sys.argv:
        actual = REQUIREMENTS.read_text(encoding="utf-8") if REQUIREMENTS.exists() else ""
        if actual != expected:
            print("backend/requirements.txt is stale — run: python scripts/sync_requirements.py")
            return 1
        print(f"ok    requirements.txt matches pyproject ({expected.count(chr(10)) - 3} deps)")
        return 0

    REQUIREMENTS.write_text(expected, encoding="utf-8")
    print(f"wrote {REQUIREMENTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
