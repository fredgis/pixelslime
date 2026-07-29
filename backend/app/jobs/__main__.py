"""Command multiplexer for ``python -m app.jobs daily|backfill|seed``.

The command can also be selected with the ``PIXELSLIME_JOB`` environment variable,
which is what the Container Apps Job uses.

That indirection exists for a concrete reason. Overriding a Container Apps Job's
``command`` at start time **replaces the whole container template**, which silently
drops every environment variable the job needs -- the asmDB URL, the instance, the
bearer secret reference. A job started that way hangs with no output at all, because
it never gets far enough to log anything. Selecting the subcommand through an env var
leaves the template intact, so the job keeps its configuration.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import backfill, daily, seed

_COMMANDS = ("daily", "backfill", "seed")


def _argv_from_environment() -> list[str]:
    """Build an argv from PIXELSLIME_JOB when no command was passed on the line."""
    raw = os.environ.get("PIXELSLIME_JOB", "").strip()
    # Allows "backfill --from 2026-08-01 --to 2026-08-03" in a single variable.
    return raw.split() if raw else []


def main(argv: list[str] | None = None) -> None:
    """Dispatch one command while leaving each subcommand's arguments isolated."""
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        argv = _argv_from_environment()

    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument(
        "command",
        choices=_COMMANDS,
        help="Subcommand to run. May also be supplied via the PIXELSLIME_JOB env var.",
    )
    args, remainder = parser.parse_known_args(argv)

    if args.command == "daily":
        if remainder:
            parser.error("daily takes no arguments")
        daily.main()
    elif args.command == "backfill":
        backfill.main(remainder)
    else:
        if remainder:
            parser.error("seed takes no arguments")
        seed.main()


if __name__ == "__main__":
    main()
