"""Command multiplexer for ``python -m app.jobs daily|backfill|seed``."""

from __future__ import annotations

import argparse

from . import backfill, daily, seed


def main(argv: list[str] | None = None) -> None:
    """Dispatch one command while leaving each subcommand's arguments isolated."""
    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument("command", choices=("daily", "backfill", "seed"))
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
