"""Build the PSC-1 preset DEFLATE dictionary and measure what it actually buys us.

A zlib preset dictionary primes the sliding window with text the compressor is
allowed to reference before it has seen any input. On strings as short as a card's
(roughly 180 characters across five fields) plain DEFLATE is close to useless — there
simply is not enough history to find matches in. Primed with the vocabulary these
cards are actually written in, the same 180 characters compress dramatically better.

DEFLATE prefers matches near the END of the dictionary, so the corpus below is ordered
least useful first, most useful last.

Usage:  python scripts/build_dict.py
Writes: assets/psdict_v1.bin   (pinned by version 0x01 in the PSC-1 header)
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "psdict_v1.bin"
MAX_DICT = 32768  # zlib's window; anything earlier is unreachable

SEP = "\x1f"

# ── least valuable first, most valuable last ────────────────────────────────────

TYPES_AND_TIERS = (
    "FAIRY FOREST WATER EMBER STORM STONE SUGAR GHOST METAL COSMIC BLOOM FROST "
    "SLUDGE BEAM PAPER DREAM COMMON UNCOMMON RARE EPIC LEGENDARY MYTHIC "
    "Puddle Dewdrop Prism Aurora Starlight Dreamdrop "
)

NAME_PARTS = (
    "Mochi Mochibo Fernwick Blorbit Puddington Kinaco Ashmallow Nibblewisp "
    "Glimmerpuff Cobblenop Zapkin Origamew Frostbun Pudding Marshmallow Bubblegum "
    "puff bo kin wick bit ton co low wisp nop mew bun let ling kit pip "
)

SCENERY = (
    "in the forest at dusk under the window on a warm cushion beside the stove "
    "in a cozy reading room on a mossy stone by the garden wall in an attic at midnight "
    "in a rainy street at a bus stop in an old sweet shop on a rooftop observatory "
    "in a stationery drawer at a campfire in the first snow of the morning "
    "in a sunbeam in a quiet library in a greenhouse on a kitchen shelf "
)

# The five text fields, written the way the model is prompted to write them.
PERSONALITY = (
    "Sweet and cuddly. Loves cozy places and spreading joy! "
    "Quiet and patient. Naps under ferns and hums to beetles. "
    "Dreamy stargazer. Hums the sound of a distant satellite. "
    "Polite little puddle. Apologises for being damp. "
    "Warm, slightly singed, always a little too close to the fire. "
    "Shy and gentle. Steals biscuits and leaves a thank-you note. "
    "Heavy, dependable, absolutely refuses to hurry. "
    "Overexcited cloudlet. Vibrates when happy, which is always. "
    "Folds itself into whatever shape the moment requires. "
    "Cold on the outside, suspiciously warm in the middle. "
    "Curious and clever. Collects small shiny things. "
    "Cheerful and clumsy. Trips over absolutely nothing. "
    "Serene and slow. Has never once been in a hurry. "
    "Bright and bouncy. Cannot sit still for more than a moment. "
    "Loves naps, warm light, and being told it is doing well. "
)

POWER_NAMES = (
    "Sugar Squish Moss Hug Orbit Drop Splish Bow Dust Bloom Toast Puff Crumb Fade "
    "Lullabloom Static Boop Crease Step Snow Nap Gentle Wobble Bubble Shield "
    "Sparkle Rush Cozy Field Pillow Slam Glow Up Soft Landing "
)

POWER_DESC = (
    "Covers the area in sweet goo, healing allies over time. "
    "Wraps a friend in warm moss, blocking the next hit. "
    "Calls down a tiny meteor of pure glitter. "
    "A courteous splash that slows everyone nearby. "
    "Puffs up golden-brown and radiates cosy heat. "
    "Vanishes into crumbs and reappears behind the target. "
    "Everyone nearby takes a short, extremely good nap. "
    "A tiny shock that makes everyone's hair stand up. "
    "Folds flat, slips through the gap, unfolds behind you. "
    "Freezes the ground into a soft, very comfy drift. "
    "Raises a shimmering bubble that absorbs one attack. "
    "Boosts the happiness of every ally for a short while. "
    "Restores a little energy to the whole party. "
    "Bounces harmlessly off and hits twice as hard. "
)

QUOTES = (
    "Mochi! (Hugs all around!) Puni! (five more minutes) Blorb! (I saw the whole sky!) "
    "Plip! (Terribly sorry.) Kina! (Taste the sunshine!) Fwoosh! (Perfectly toasted.) "
    "Fuwa! (still warm inside!) Shhh... (you are almost there) BZZT! (did you feel that?!) "
    "Poyo! (Let us be friends!) Nya! (I learned this from a cat!) "
)

# The single most valuable block: the exact glue that appears in every card.
GLUE = (
    "and the a an of in on to with for it is are was its their they them "
    "loves likes hates enjoys prefers always never sometimes very quite rather "
    "little tiny small big warm cold soft sweet gentle quiet bright happy sleepy "
    "friend friends ally allies nearby around over time short while moment "
    "! . , ' ( ) "
    "Loves cozy places and spreading joy! "
    "healing allies over time. "
    "Sweet and cuddly. "
    "(Hugs all around!) "
)

CORPUS = "".join([
    TYPES_AND_TIERS, NAME_PARTS, SCENERY,
    PERSONALITY, POWER_NAMES, POWER_DESC, QUOTES, GLUE,
])


def build() -> bytes:
    data = CORPUS.encode("utf-8")
    return data[-MAX_DICT:]  # keep the tail; the head would be unreachable anyway


def bundle(card: dict) -> bytes:
    return SEP.join([
        card["name"], card["personality"], card["power_name"],
        card["power_desc"], card["quote"],
    ]).encode("utf-8")


def deflate(payload: bytes, zdict: bytes | None) -> bytes:
    kw = {"zdict": zdict} if zdict else {}
    c = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15, **kw)
    return c.compress(payload) + c.flush()


def inflate(blob: bytes, zdict: bytes | None) -> bytes:
    kw = {"zdict": zdict} if zdict else {}
    d = zlib.decompressobj(wbits=-15, **kw)
    return d.decompress(blob) + d.flush()


def main() -> None:
    zdict = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(zdict)
    print(f"dictionary : {OUT.relative_to(ROOT)}  {len(zdict):,} bytes")
    print(f"sha256     : {__import__('hashlib').sha256(zdict).hexdigest()[:32]}\n")

    HEADER, ROW, MAX_ROWS = 32, 140, 4
    print(f"{'card':<12} {'raw':>5} {'plain':>6} {'dict':>5} {'saved':>6} {'stream':>7} {'rows':>5}")
    print("-" * 52)

    worst = 0
    for f in sorted((ROOT / "contracts" / "cards").glob("*.json")):
        card = json.loads(f.read_text(encoding="utf-8"))
        raw = bundle(card)
        plain = deflate(raw, None)
        packed = deflate(raw, zdict)

        assert inflate(packed, zdict) == raw, f"round-trip failed for {f.name}"

        stream = HEADER + len(packed)
        rows = -(-stream // ROW)
        worst = max(worst, rows)
        saved = 100 * (1 - len(packed) / len(plain))
        print(f"{f.stem:<12} {len(raw):>5} {len(plain):>6} {len(packed):>5} {saved:>5.0f}% "
              f"{stream:>7} {rows:>5}")

    print("-" * 52)
    print(f"worst case: {worst} row(s), limit is {MAX_ROWS}")
    assert worst <= MAX_ROWS, "a card exceeded the 4-row ceiling"


if __name__ == "__main__":
    main()
