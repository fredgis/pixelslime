/**
 * PSC-1 provenance helpers for the MSW mock.
 *
 * The SLIME PROFILE provenance panel is a genuine differentiator, so the mock does
 * not fake it with random glyphs: it packs each card into a deterministic byte
 * stream, Z85-encodes it for real (the exact ZeroMQ Z85 alphabet), splits it into
 * asmDB rows of ≤175 characters, and anchors it with a real keccak-256 hash — the
 * same primitive Ethereum uses. W7 will compute the true on-chain bytes; this module
 * mirrors the *shape* of that so the panel feels like a treasure, not a debug dump.
 *
 * This file is only ever imported by the mock, which is dynamically loaded when
 * `VITE_USE_MOCK` is on, so none of it reaches the production bundle.
 */

/** ZeroMQ Z85 alphabet (RFC 32/Z85). */
const Z85_ALPHABET =
  '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#';

/** Encode bytes as Z85. Input is zero-padded to a multiple of 4 bytes. */
export function z85Encode(input: Uint8Array): string {
  const padded = input.length % 4 === 0 ? input : padTo(input, input.length + (4 - (input.length % 4)));
  let out = '';
  for (let i = 0; i < padded.length; i += 4) {
    let value =
      padded[i] * 0x1000000 + padded[i + 1] * 0x10000 + padded[i + 2] * 0x100 + padded[i + 3];
    const chars = new Array<string>(5);
    for (let j = 4; j >= 0; j -= 1) {
      chars[j] = Z85_ALPHABET[value % 85];
      value = Math.floor(value / 85);
    }
    out += chars.join('');
  }
  return out;
}

function padTo(input: Uint8Array, length: number): Uint8Array {
  const out = new Uint8Array(length);
  out.set(input);
  return out;
}

/** Split a string into chunks of at most `size` characters. */
export function chunk(text: string, size: number): string[] {
  const out: string[] = [];
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size));
  return out;
}

/* ─────────────────────────── keccak-256 ─────────────────────────── */

const RC: bigint[] = [
  0x0000000000000001n, 0x0000000000008082n, 0x800000000000808an, 0x8000000080008000n,
  0x000000000000808bn, 0x0000000080000001n, 0x8000000080008081n, 0x8000000000008009n,
  0x000000000000008an, 0x0000000000000088n, 0x0000000080008009n, 0x000000008000000an,
  0x000000008000808bn, 0x800000000000008bn, 0x8000000000008089n, 0x8000000000008003n,
  0x8000000000008002n, 0x8000000000000080n, 0x000000000000800an, 0x800000008000000an,
  0x8000000080008081n, 0x8000000000008080n, 0x0000000080000001n, 0x8000000080008008n,
];
const R = [
  [0, 36, 3, 41, 18],
  [1, 44, 10, 45, 2],
  [62, 6, 43, 15, 61],
  [28, 55, 25, 21, 56],
  [27, 20, 39, 8, 14],
];
const MASK = (1n << 64n) - 1n;

function rotl(x: bigint, n: number): bigint {
  const s = BigInt(n);
  return ((x << s) | (x >> (64n - s))) & MASK;
}

function keccakF(state: bigint[]): void {
  for (let round = 0; round < 24; round += 1) {
    const c = new Array<bigint>(5);
    for (let x = 0; x < 5; x += 1) {
      c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20];
    }
    const d = new Array<bigint>(5);
    for (let x = 0; x < 5; x += 1) {
      d[x] = c[(x + 4) % 5] ^ rotl(c[(x + 1) % 5], 1);
    }
    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) state[x + 5 * y] ^= d[x];
    }

    const b = new Array<bigint>(25).fill(0n);
    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) {
        b[y + 5 * ((2 * x + 3 * y) % 5)] = rotl(state[x + 5 * y], R[x][y]);
      }
    }
    for (let x = 0; x < 5; x += 1) {
      for (let y = 0; y < 5; y += 1) {
        state[x + 5 * y] = b[x + 5 * y] ^ (~b[((x + 1) % 5) + 5 * y] & b[((x + 2) % 5) + 5 * y]);
      }
    }
    state[0] ^= RC[round];
  }
}

/**
 * keccak-256 (Ethereum flavour: 0x01 domain padding, 136-byte rate). Returns the
 * 32-byte digest as a `0x`-prefixed lowercase hex string.
 */
export function keccak256(input: Uint8Array): string {
  const rate = 136;
  const state = new Array<bigint>(25).fill(0n);
  const padded = new Uint8Array(Math.ceil((input.length + 1) / rate) * rate);
  padded.set(input);
  padded[input.length] ^= 0x01;
  padded[padded.length - 1] ^= 0x80;

  for (let offset = 0; offset < padded.length; offset += rate) {
    for (let i = 0; i < rate / 8; i += 1) {
      let lane = 0n;
      for (let b = 0; b < 8; b += 1) {
        lane |= BigInt(padded[offset + i * 8 + b]) << BigInt(8 * b);
      }
      state[i] ^= lane;
    }
    keccakF(state);
  }

  let hex = '';
  for (let i = 0; i < 4; i += 1) {
    let lane = state[i];
    for (let b = 0; b < 8; b += 1) {
      hex += Number(lane & 0xffn).toString(16).padStart(2, '0');
      lane >>= 8n;
    }
  }
  return `0x${hex}`;
}
