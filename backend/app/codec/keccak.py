"""keccak256 — the Ethereum hash variant, in pure Python.

``card_hash`` is what gets minted on-chain, so it must be **keccak256 as Ethereum
uses it**, not NIST SHA3-256. The two share the Keccak-f[1600] permutation but
differ in one byte of padding (``0x01`` domain suffix here versus ``0x06`` for
SHA3-256), which produces completely different digests. Silently substituting
``hashlib.sha3_256`` would therefore break the on-chain anchor, so this is
implemented from scratch rather than risk that mistake — it depends on no
third-party package. Known answer: ``keccak256(b"")`` starts ``0xc5d24601``.

See ``docs/CODEC.md`` §6 (``card_hash``) and §4.4 (the anchor row).
"""

from __future__ import annotations

_MASK64 = (1 << 64) - 1
_RATE = 136  # bytes absorbed per permutation for a 256-bit capacity-512 sponge
_OUTPUT = 32  # digest length in bytes

# Round constants for the iota step (24 rounds).
# fmt: off
_RC: tuple[int, ...] = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
# fmt: on

# Rotation offsets for the rho step, indexed ``_ROT[x][y]``.
_ROT: tuple[tuple[int, ...], ...] = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rol(value: int, shift: int) -> int:
    """Rotate a 64-bit lane left by ``shift`` bits."""
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(state: list[list[int]]) -> None:
    """Apply the 24-round Keccak-f[1600] permutation in place.

    ``state`` is a 5x5 matrix of 64-bit lanes indexed ``state[x][y]``.
    """
    for rc in _RC:
        # theta
        col = [
            state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)
        ]
        d = [col[(x - 1) % 5] ^ _rol(col[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]
        # rho and pi
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(state[x][y], _ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        # iota
        state[0][0] ^= rc


def keccak256(data: bytes) -> bytes:
    """Return the 32-byte keccak256 digest of ``data`` (Ethereum variant)."""
    # Multi-rate padding pad10*1 with Keccak's 0x01 domain suffix.
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _RATE != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    state = [[0] * 5 for _ in range(5)]
    for offset in range(0, len(padded), _RATE):
        block = padded[offset : offset + _RATE]
        for i in range(_RATE // 8):
            lane = int.from_bytes(block[8 * i : 8 * i + 8], "little")
            state[i % 5][i // 5] ^= lane
        _keccak_f1600(state)

    out = bytearray()
    for i in range(_OUTPUT // 8):
        out += state[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out[:_OUTPUT])
