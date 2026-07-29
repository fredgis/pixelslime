# PSC-1 — PixelSlime Card codec, version 1

> **Normative specification.** `backend/app/codec/` implements exactly this document.
> Where code and document disagree, this document is wrong and must be fixed — never the other way round.

---

## 1. Why this exists

An asmDB row gives us **175 bytes of UTF-8 text** for `content`, with **no NUL, no CR and no LF**
(enforced by the service — see `repo-asmdb/saas/sidecar/tsv.go`). A whole trading card has to survive in
that. PSC-1 is how.

Two consequences drive every decision below:

1. **`content` is text, not binary.** Raw bytes cannot be stored — they would contain `0x00` and invalid
   UTF-8 sequences. A text envelope is mandatory.
2. **One row is not enough.** Even a tightly packed card overruns 175 bytes once the text is included, so
   a card is stored as **a short run of rows**, addressed arithmetically.

---

## 2. The envelope: Z85

Binary is encoded with **Z85** (the ZeroMQ base-85 alphabet), chosen over base64 for density and over
base91 for simplicity.

```
Alphabet (85 symbols, index 0..84):
0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#
```

The alphabet contains **no backslash, no space, no tab, no quote, no CR, no LF and no NUL**, so an
encoded payload is safe against the engine's internal TSV escaping and against the 511-byte
command-line limit.

| | |
|---|---|
| Ratio | **4 binary bytes → 5 characters** |
| Capacity of one `content` field | `floor(175 / 5) × 4` = **140 binary bytes** |

### 2.1 Encoding

Input is padded with `0x00` to a multiple of 4. Each 4-byte group is read as a **big-endian `uint32`**
and emitted as 5 characters, most significant digit first:

```
value = b0<<24 | b1<<16 | b2<<8 | b3
for i in 4..0:  out += ALPHABET[(value / 85^i) mod 85]
```

The true unpadded length is **not** encoded by Z85 — it is carried by `total_len` in the header
(§3), so decoders always know how many trailing pad bytes to discard.

### 2.2 Decoding

Inverse of the above. A decoder **must reject** any character outside the alphabet, and any chunk whose
`uint32` value exceeds `0xFFFFFFFF`.

---

## 3. The byte stream

A card is serialised into **one continuous byte stream**:

```
┌────────────────────────┬──────────────────────────────────────────┐
│ HEADER — 32 bytes      │ BODY — DEFLATE-compressed text, variable │
└────────────────────────┴──────────────────────────────────────────┘
```

### 3.1 Header — exactly 32 bytes, little-endian

| Off | Size | Field | Type | Notes |
|---:|---:|---|---|---|
| 0 | 1 | `magic` | `u8` | always `0x50` (`'P'`) |
| 1 | 1 | `version` | `u8` | `0x01`. Also pins the DEFLATE dictionary version. |
| 2 | 2 | `serial` | `u16` | card number, `1..65535` |
| 4 | 2 | `total_len` | `u16` | total stream length in bytes, header included |
| 6 | 1 | `level` | `u8` | `1..100` |
| 7 | 1 | `flags_rarity_type` | `u8` | bitfield, see §3.2 |
| 8 | 2 | `height_mm` | `u16` | |
| 10 | 2 | `weight_g` | `u16` | |
| 12 | 1 | `strength` | `u8` | `0..100` |
| 13 | 1 | `endurance` | `u8` | `0..100` |
| 14 | 1 | `agility` | `u8` | `0..100` |
| 15 | 1 | `happiness` | `u8` | `0..100` |
| 16 | 1 | `art_id` | `u8` | |
| 17 | 1 | `style_id` | `u8` | |
| 18 | 1 | `frame_id` | `u8` | |
| 19 | 1 | `background_id` | `u8` | |
| 20 | 1 | `biome_id` | `u8` | |
| 21 | 1 | `mood_id` | `u8` | |
| 22 | 2 | `flags` | `u16` | see §3.3 |
| 24 | 2 | `mint_day` | `u16` | days since **2026-01-01** (day 0) |
| 26 | 4 | `art_sha` | `u8[4]` | first 4 bytes of the PNG's SHA-256. **When the card has no artwork yet, this is `00 00 00 00`** and decodes back to the string `"00000000"`. The field is never absent in the stream — the header always reserves the 4 bytes. |
| 30 | 2 | `crc16` | `u16` | CRC-16/CCITT-FALSE over bytes `0..29` **and** the whole body |

### 3.2 `flags_rarity_type` (offset 7)

```
bit  7 6 5 4 3 2 1 0
     │ │ │ │ │ │ │ └── rarity, 3 bits (0..5)
     │ │ │ │ └─┴─┴──── (rarity continues)
     │ │ │ │
     └─┴─┴─┴────────── type, 4 bits (0..15)   ← bits 3..6
                       bit 7 = shiny
```

Precisely:

| Bits | Field | Values |
|---|---|---|
| `0..2` | `rarity` | `0` COMMON · `1` UNCOMMON · `2` RARE · `3` EPIC · `4` LEGENDARY · `5` MYTHIC |
| `3..6` | `type` | index into the type table, §3.5 |
| `7` | `shiny` | `0` or `1` |

```python
packed = (rarity & 0x07) | ((type_id & 0x0F) << 3) | ((shiny & 1) << 7)
rarity  =  packed        & 0x07
type_id = (packed >> 3)  & 0x0F
shiny   = (packed >> 7)  & 0x01
```

### 3.3 `flags` (offset 22, `u16`)

| Bits | Meaning |
|---:|---|
| 0 | has a companion animal |
| 1 | has an accessory |
| 2 | vision-verified |
| 3 | anchored on-chain |
| 4 | seed card (not produced by the daily job) |
| **5..10** | **`companion_id`** — 6 bits, index into the companion table (0..63). Meaningful only when bit 0 is set; **must be 0 when bit 0 is clear.** |
| 11..15 | reserved, **must be 0** in version 1 |

```python
packed = (bits0_4
          | ((companion_id & 0x3F) << 5))
companion_id = (packed >> 5) & 0x3F
```

> **Why this exists.** Without it, the specific companion is unrecoverable from the stream: only the
> boolean survives, so a card read back from the database could say *"has a companion"* but never say
> *which one*. W7 hit exactly that gap while building the profile endpoint. The reserved bits were
> there for precisely this kind of omission.

### 3.4 Display fields resolved from ids

Three fields shown in the UI are **not stored as text** — they are looked up from the ids in the header.
The tables are frozen alongside the enums in §3.5 and live in `contracts/lookups.json`.

| Display field | Resolved from | Table |
|---|---|---|
| `biome` | `biome_id` | `biomes` |
| `mood` | `mood_id` | `moods` |
| `companion` | `companion_id` (flags bits 5..10), when bit 0 is set | `companions` |

This is what keeps the card text budget spent on the fields that are genuinely free-form.

### 3.5 Enumerations

Ordinals are **frozen**. Never reorder; only append.

```
rarity : COMMON UNCOMMON RARE EPIC LEGENDARY MYTHIC
type   : FAIRY FOREST WATER EMBER STORM STONE SUGAR GHOST
         METAL COSMIC BLOOM FROST SLUDGE BEAM PAPER DREAM
```

### 3.6 Body — the text bundle

Five text fields are joined with a single **`0x1F`** (unit separator) in this exact order:

```
name  0x1F  personality  0x1F  power_name  0x1F  power_desc  0x1F  quote
```

The joined string is encoded **UTF-8**, then compressed with **raw DEFLATE** using a **preset
dictionary**:

```python
c = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15, zdict=DICT)
body = c.compress(joined) + c.flush()
```

- `wbits=-15` → raw DEFLATE, no zlib header, no trailer.
- `zdict` → `assets/psdict_v1.bin`, pinned by `version = 0x01`.
- Decompression uses `zlib.decompressobj(wbits=-15, zdict=DICT)`.

> **The dictionary is the whole trick.** On strings this short, DEFLATE alone barely helps. Primed with
> the PixelSlime vocabulary it typically saves 35–50 %, which is what lets the median card fit in one row.

### 3.7 Field length limits

Enforced at **encode** time. Exceeding any of them is an error, never a truncation.

> **Character limits and byte limits are two separate checks, and both are enforced.** A character can
> occupy up to 4 UTF-8 bytes, so `name` at 18 characters may still be 36 bytes. The schema in
> `contracts/card.schema.json` expresses the character limits; the byte limits below exist because the
> byte budget is what the row is actually measured in. Check both.

| Field | Max characters | Max UTF-8 bytes |
|---|---:|---:|
| `name` | 18 | 36 |
| `personality` | 90 | 180 |
| `power_name` | 20 | 40 |
| `power_desc` | 90 | 180 |
| `quote` | 40 | 80 |

None of the five may contain `0x1F`, `0x00`, `\r` or `\n`.

---

## 4. Rows

### 4.1 Addressing

```
row_id = serial × 16 + part          part ∈ 0..15
```

| `part` | Contents |
|---:|---|
| `0` | stream bytes `0 .. 139` — header plus the start of the body |
| `1..3` | stream bytes `140k .. 140k+139`, continuation |
| `8` | on-chain anchor, see §4.4 |
| `9..15` | reserved |

The stream is split into **140-byte chunks**; chunk `k` goes to `part = k`.
A card **must not** exceed **4 chunks (560 bytes)**. Encoders raise an error beyond that.

The reader gets `total_len` from part 0 and computes `ceil(total_len / 140)` — it never guesses and never
scans.

### 4.2 `value` — the only filterable column

| Row | `value` |
|---|---|
| `part = 0` | mint date as **`YYYYMMDD`**, e.g. `20260728` — always **positive** |
| `part ≥ 1` | **`-(serial × 16 + part)`** — always **negative** |

This is what makes `GET /v1/range?lo=20260728&hi=20260728` return **exactly one row**, the header of the
card of the day. Continuation rows can never pollute a result whose `lo ≥ 0`.

### 4.3 `tag`

```
psc.<serial>.<part>        e.g.  psc.1.0
```

≤ 39 bytes, single token, no spaces. Makes `GET /v1/find?q=psc.42.` recover every row of a card.

### 4.4 The anchor row, `part = 8`

Written after a successful on-chain mint.

| Off | Size | Field |
|---:|---:|---|
| 0 | 1 | `magic` = `0x41` (`'A'`) |
| 1 | 1 | `version` = `0x01` |
| 2 | 2 | `serial` |
| 4 | 8 | first 8 bytes of the transaction hash |
| 12 | 4 | block number (`u32`) |
| 16 | 4 | `tokenId` (`u32`) |
| 20 | 8 | first 8 bytes of `cardHash` (keccak256 of the full stream) |

28 bytes → 35 Z85 characters. `value` = `-(serial × 16 + 8)`, `tag` = `psc.<serial>.8`.

---

## 5. Required behaviour

An implementation is correct only if all of these hold.

1. **Round-trip.** `decode(encode(card)) == card` over the **encoded fields only**, for every fixture in
   `contracts/cards/` and for 10,000 randomly generated valid cards.

   > **Encoded fields are exactly those listed in §3.1 and §3.6.** `biome` and `companion` are
   > **display-only**: `contracts/card.schema.json` marks them "NOT encoded in PSC-1", they never enter
   > the stream, and they are therefore unrecoverable by definition. An implementation must drop them
   > when constructing the canonical `Card`, so that round-trip equality is well defined.
   >
   > *(An earlier revision of this document demanded equality "for every field", which was impossible to
   > satisfy — W2 found the contradiction while implementing it. This is the corrected wording.)*
2. **Determinism.** `encode(card)` is byte-identical across runs, processes and machines.
3. **Loud failure.** Over-long fields, an out-of-range enum, a stream over 560 bytes, a bad CRC or a
   missing continuation row all raise. Nothing is ever silently truncated or defaulted.
4. **CRC.** `crc16` is computed over header bytes `0..29` concatenated with the body, with the `crc16`
   field itself excluded. A decoder verifies it and raises on mismatch.
5. **Text safety.** Every emitted `content` string is valid UTF-8, ≤ 175 bytes, and contains no `0x00`,
   `\r` or `\n`. **Enforce this with an explicit `raise` inside `encode`, not with `assert`** — `assert`
   is stripped under `python -O`, and this is the one invariant asmDB will reject us for.
6. **Mochibo fits.** The reference card in `contracts/cards/mochibo.json` encodes to **at most 2 rows**.
   *(Measured: 1 row, 52-byte stream, 65 of the 175 available bytes used.)*

---

## 6. Public API

```python
def encode(card: Card) -> list[Row]:
    """Card → ordered asmDB rows. Raises CodecError on any violation."""

def decode(rows: list[Row]) -> Card:
    """asmDB rows → Card. Order-insensitive. Raises CodecError on any violation."""

def encode_stream(card: Card) -> bytes:   # the raw PSC-1 stream, pre-Z85
def card_hash(card: Card) -> bytes:       # keccak256(encode_stream(card)) — the on-chain anchor
```

`Row` is `{id: int, value: int, tag: str, content: str}`.

> `card_hash` is what gets minted on-chain. It must be computed from the **stream**, never from the JSON,
> because the stream is the canonical form and JSON key order is not.
