"""Z85 — the text envelope that lets binary survive an asmDB ``content`` column.

``content`` is UTF-8 text with no NUL, CR or LF (enforced server-side), so raw
bytes cannot be stored there. Z85 (the ZeroMQ base-85 alphabet) is used rather
than base64 for density — 4 binary bytes become exactly 5 characters, giving
``floor(175 / 5) * 4 = 140`` binary bytes per row — and rather than base91 for
simplicity. Crucially its alphabet contains no backslash, space, tab, quote, CR,
LF or NUL, so an encoded payload cannot collide with the engine's TSV escaping.

The true unpadded length is **not** carried here (Z85 always rounds up to a
multiple of four bytes); ``header.total_len`` tells the decoder how many trailing
pad bytes to drop. See ``docs/CODEC.md`` §2.
"""

from __future__ import annotations

from .errors import Z85Error

# Alphabet, index 0..84. Order is normative — do not sort it.
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#"

if len(ALPHABET) != 85 or len(set(ALPHABET)) != 85:  # pragma: no cover - startup invariant
    raise Z85Error("Z85 alphabet must be 85 unique symbols")

_DECODE: dict[str, int] = {c: i for i, c in enumerate(ALPHABET)}

_UINT32_MAX = 0xFFFFFFFF
_POW85 = (85**4, 85**3, 85**2, 85, 1)


def z85_encode(data: bytes) -> str:
    """Encode arbitrary bytes to Z85 text, zero-padding to a multiple of four.

    Padding is deliberate and lossy in isolation: the number of pad bytes is not
    recoverable from the text alone, only from ``total_len`` in the PSC-1 header.
    """
    pad = (-len(data)) % 4
    buf = data + b"\x00" * pad
    out: list[str] = []
    for i in range(0, len(buf), 4):
        value = int.from_bytes(buf[i : i + 4], "big")
        chars = [""] * 5
        for j in range(5):
            value, rem = divmod(value, 85)
            chars[4 - j] = ALPHABET[rem]
        out.append("".join(chars))
    return "".join(out)


def z85_decode(text: str) -> bytes:
    """Decode Z85 text back to bytes (still padded to a multiple of four).

    Rejects any character outside the alphabet and any 5-symbol group whose value
    overflows a ``uint32`` — both are impossible in a well-formed stream and must
    fail loudly rather than yield silent garbage.
    """
    if len(text) % 5 != 0:
        raise Z85Error(f"Z85 length must be a multiple of 5, got {len(text)}")
    out = bytearray()
    for i in range(0, len(text), 5):
        value = 0
        for j in range(5):
            ch = text[i + j]
            digit = _DECODE.get(ch)
            if digit is None:
                raise Z85Error(f"invalid Z85 character {ch!r} at offset {i + j}")
            value += digit * _POW85[j]
        if value > _UINT32_MAX:
            raise Z85Error(f"Z85 group at offset {i} overflows uint32")
        out += value.to_bytes(4, "big")
    return bytes(out)
