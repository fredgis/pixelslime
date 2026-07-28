"""Prove every row the codec emits is legal for asmDB, using asmDB's own rules.

The rules below are transcribed from the real server-side validator at
repo-asmdb/saas/sidecar/tsv.go, not from our own documentation. If the codec
and the service ever disagree, this is where it shows up — before a write is
attempted rather than as a remote 4xx at 10:00 in the morning.

Usage:  python scripts/verify_rows.py
"""
from __future__ import annotations

import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.codec import card_hash, decode, encode, encode_stream  # noqa: E402
from app.codec.card import Card  # noqa: E402

CARDS = pathlib.Path(__file__).resolve().parent.parent / "contracts" / "cards"


def asmdb_violations(row: object) -> list[str]:
    """Exactly what saas/sidecar/tsv.go rejects."""
    content: str = row.content  # type: ignore[attr-defined]
    tag: str = row.tag  # type: ignore[attr-defined]
    row_id: int = row.id  # type: ignore[attr-defined]
    out: list[str] = []

    n = len(content.encode("utf-8"))
    if n > 175:
        out.append(f"content is {n} bytes, limit 175")
    if any(ch in content for ch in "\r\n\x00"):
        out.append("content contains CR, LF or NUL")

    t = len(tag.encode("utf-8"))
    if not tag:
        out.append("tag is empty")
    if t > 39:
        out.append(f"tag is {t} bytes, limit 39")
    if any(ch in tag for ch in " \t\r\n\x00"):
        out.append("tag contains space, tab, CR, LF or NUL")

    if row_id < 1:
        out.append("id must be >= 1")
    return out


def main() -> int:
    failures = 0
    print(f"{'fixture':<20}{'rows':>5}{'stream':>8}{'widest':>8}   {'value signs':<12} status")
    print("-" * 72)

    for f in sorted(CARDS.glob("*.json")):
        card = Card.model_validate_json(f.read_text(encoding="utf-8"))
        rows = encode(card)
        stream = encode_stream(card)

        # decode must not care about row order
        if decode(list(reversed(rows))) != card:
            print(f"{f.stem:<20} ROUND-TRIP FAILED")
            failures += 1
            continue

        bad = [v for r in rows for v in asmdb_violations(r)]
        widest = max(len(r.content.encode("utf-8")) for r in rows)
        signs = "".join("+" if r.value > 0 else "-" for r in rows)

        # the index invariant: header positive, continuations negative
        if rows[0].value <= 0 or any(r.value >= 0 for r in rows[1:]):
            bad.append("value sign convention broken - RANGE would return continuation rows")

        status = "OK" if not bad else "; ".join(bad)
        failures += bool(bad)
        print(f"{f.stem:<20}{len(rows):>5}{len(stream):>8}{widest:>8}   {signs:<12} {status}")

    print()
    mochibo = Card.model_validate_json((CARDS / "mochibo.json").read_text(encoding="utf-8"))
    row = encode(mochibo)[0]
    print("Mochibo, row 0, exactly as it will sit in smilesdb:")
    print(f"  id      {row.id}          (serial*16 + part)")
    print(f"  value   {row.value}   (YYYYMMDD, positive => header row)")
    print(f"  tag     {row.tag}")
    print(f"  content {row.content}")
    print(f"  bytes   {len(row.content.encode('utf-8'))} of 175")
    print(f"  hash    0x{card_hash(mochibo).hex()}")

    print()
    print("all rows legal for asmDB" if not failures else f"{failures} fixture(s) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
