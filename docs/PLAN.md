# 🫧 PIXELSLIME — Complete Project Plan

> **Status: PLAN — awaiting GO.** No application code is written until this document is approved.
> A clickable static mockup ships alongside it at `docs/mockup/index.html`.

| | |
|---|---|
| **Product name** | **PIXELSLIME — ぷにぷにパラダイス** *(PuniPuni Paradise)* |
| **Pitch** | One unique AI-generated PixelSlime card **every day**, showcased in the "SLIMEDEX" gallery, and (phase 2) anchored on a blockchain with the **$SMILE** token. |
| **Access** | **Public site — no sign-in.** Secrets stay server-side: asmDB bearer in Key Vault, AI models via the backend's managed identity. |
| **Entra tenant** | `<TENANT_ID>` (for Azure resources only) |
| **Subscription** | `<SUBSCRIPTION_ID>` (<SUBSCRIPTION_NAME>) |
| **Resource group** | `FGI-ASMDBPIXELSMILES` — **swedencentral** (currently empty) |
| **asmDB database** | `https://www.asmdb.cloud/db/<ASMDB_INSTANCE>` (`smilesdb`, engine 1.7.0, **0 rows**) |
| **AI models** | `gpt-image-2`, `gpt-5.6-sol`, `MAI-Image-2.5-Pro` on account `fgi` (RG `FGI-AI`) |

---

## Table of contents

1. [What I verified up front](#1-what-i-verified-up-front-measured-facts-not-assumptions)
2. [The universe: lore, brand, visual identity](#2-the-universe-lore-brand-visual-identity)
3. [Target Azure architecture](#3-target-azure-architecture)
4. [The core problem: fitting a card into asmDB](#4-the-core-problem-fitting-a-card-into-asmdb)
5. [The AI generation pipeline](#5-the-ai-generation-pipeline)
6. [The web application](#6-the-web-application)
7. [Security (public site)](#7-security-public-site)
8. [Phase 2: blockchain & the $SMILE token](#8-phase-2-blockchain--the-smile-token)
9. [Multi-agent development plan](#9-multi-agent-development-plan)
10. [Repository layout](#10-repository-layout)
11. [Milestones](#11-milestones)
12. [Risks, costs and open decisions](#12-risks-costs-and-open-decisions)
13. [What I need from you before the GO](#13-what-i-need-from-you-before-the-go)

---

## 1. What I verified up front (measured facts, not assumptions)

I probed the live APIs before writing this plan. These results **constrain the architecture** — several
natural assumptions turned out to be wrong.

### 1.1 The `gpt-image-2` image service

Endpoint: `https://fgi.services.ai.azure.com/openai/v1/images/generations`

| Question | Measured result | Consequence |
|---|---|---|
| **API key auth disabled** | An `Authorization: Bearer <Entra token>` from `az account get-access-token --resource https://cognitiveservices.azure.com` works (returns HTTP 400 validation errors, never 401). | ✅ Your constraint is confirmed: **a managed identity is required**, no keys. A `Cognitive Services User` role on account `fgi` is sufficient. |
| `background` | Accepted values: **`transparent`**, `opaque`, `auto` | ✅ The **transparent background outside the card** you asked for is natively supported. |
| `output_format` | `png` \| `jpeg` | We force `png` (alpha required). |
| `quality` | `low` \| `medium` \| `high` \| `auto` | We use `high`. |
| `size` | Width and height must both be **divisible by 16** | The vertical card will be **1024×1536** (same as `mochibo.png`). ✓ 1024/16=64, 1536/16=96 |
| `n` | ≤ 10 | We generate 1 image, optionally 2 candidates for high rarities. |
| `image`, `reference_images`, `input_fidelity`, `response_format` | ❌ **Unknown parameters on `/generations`** | You cannot pass a reference image to `/generations`. |
| **`POST /openai/v1/images/edits`** | ✅ **Exists and accepts multipart** — `model` + `prompt` + `image=@mochibo.png` were all accepted (only a deliberately bogus field was rejected). | ✅ **This is how `mochibo.png` becomes the style template.** The single biggest unknown in this project is now resolved. |
| **Quota** | `GlobalStandard`, **capacity 2**, Sweden Central. Two calls close together → `429 … retry after 34 seconds`. | ⚠️ **Real risk.** The daily job (1 card) is fine, but seeding and retries need **exponential backoff that honours `Retry-After`**. A quota increase is recommended. |

### 1.2 The asmDB database

Live and empty:

```
GET https://www.asmdb.cloud/db/<ASMDB_INSTANCE>/health
→ 200 {"engine":"1.7.0","rows":0,"status":"ok","storageFormat":"2"}

GET .../v1/count   (no token)
→ 401 {"error":{"code":"unauthorized","message":"missing or invalid bearer token"}}
```

**REST contract** (source: `repo-asmdb/docs/SAAS.md`):

| Route | Body | Success |
|---|---|---|
| `GET /health` | — | `200` — **the only unauthenticated route** |
| `GET /v1/rows?limit=&offset=` | — | `200 {"rows":[…],"count":n,"hasMore":bool,"nextOffset":n}` |
| `GET /v1/rows/{id}` | — | `200 {"row":…}` / `404` |
| `POST /v1/rows` | row without timestamps | `201 {"row":…}` |
| `PUT /v1/rows/{id}` | `{value,tag,content}` | `200 {"row":…}` |
| `DELETE /v1/rows/{id}` | — | `204` |
| `GET /v1/count` | — | `200 {"count":n}` |
| `GET /v1/find?q=&limit=&offset=` | — | substring over `tag` + `content` (**full scan**) |
| `GET /v1/range?lo=&hi=&limit=&offset=` | — | rows where `lo <= value <= hi` (**full scan**) |

Three structural facts from the docs and the sidecar source:

1. **No CORS headers are sent — direct browser calls are impossible *by design*.**
   → A backend is not a convenience, it is **mandatory**. It holds the bearer token.
2. **Integers travel as JSON strings** (a `u64` does not survive a JS `number`).
3. **Scale-to-zero**: the free instance sleeps. The first call after idling returns `instance_starting`.
   → The client must **retry on cold start**, and the daily job must warm up (`/health`) before writing.

### 1.3 The row shape — the central constraint

An asmDB row is **exactly 256 bytes, 7 fixed columns**, and the schema never changes:

| Offset | Size | Field | Type | Notes |
|---:|---:|---|---|---|
| `0` | 8 | `id` | `u64` | primary key, **chosen by us**, ≥ 1 |
| `8` | 1 | `status` | `u8` | 0 empty · 1 live · 2 tombstone |
| `9` | 1 | `kind` | `u8` | reserved |
| `12` | 4 | `clen` | `u32` | content length |
| `16` | 8 | `created` | `i64` | epoch ms, **automatic** |
| `24` | 8 | `updated` | `i64` | epoch ms, **automatic** |
| `32` | 8 | `value` | `i64` | **the only numeric column, and the only one `RANGE` can filter on** |
| `40` | 40 | `tag` | `char[40]` | **39 usable bytes**, single token |
| `80` | 176 | `content` | `char[176]` | **175 usable bytes** |

**The validation the service actually applies** (`repo-asmdb/saas/sidecar/tsv.go`):

```go
func validateContent(s string) error {
    if !utf8.ValidString(s)               { return errors.New("content must be valid UTF-8") }
    if len([]byte(s)) > 175               { return fieldTooLong(...) }
    if strings.ContainsAny(s, "\r\n\x00") { return errors.New("content must not contain newline or NUL") }
}
func validateTag(s string) error {   // non-empty, UTF-8, ≤ 39 bytes
    if strings.ContainsAny(s, " \t\r\n\x00") { return errors.New("tag must be one token …") }
}
```

> ⚠️ **Important correction to your starting note.**
> You proposed to "store the binary directly in a `BINARY(176)` field". **That is not possible here.**
> `content` is a **valid-UTF-8 string with no NUL, CR or LF**. A raw 176-byte binary blob statistically
> contains `0x00` bytes and invalid UTF-8 sequences: it would be **rejected or corrupted**.
> A **text envelope is mandatory** — and that choice determines the real capacity.
> Handled in [§4](#4-the-core-problem-fitting-a-card-into-asmdb).

Other limits: 393,216 usable rows (free tier), 4,096 rows per transaction, engine command line
≤ 511 bytes, **no SQL, no secondary indexes, no joins**.

---

## 2. The universe: lore, brand, visual identity

### 2.1 The story — *The Great Pixel Rain*

> Long ago the world ran on 8 bits. Everything was blocky, slow and calm.
> Then a rainbow crashed somewhere above the clouds, and down came
> **the Great Pixel Rain** — ピクセルの雨.
>
> Wherever a pixel landed on something **happy** — a cushion still warm, a stone wearing moss, a hot
> chocolate forgotten on a table — the thing went soft, wobbled twice, and opened two big shiny eyes.
> The **PixelSlimes** were born.
>
> A slime does not eat. It **absorbs moods**. One that naps in a sunbeam turns warm and golden. One
> raised in a library grows clever and quiet. One that meets a cat learns to purr. That is why no two
> slimes are ever the same: **a slime is a place, a feeling and a friend, squished together**.
>
> Every dawn, exactly **one** new slime condenses out of the Rain. The **Slime Keepers** — that's you —
> must catalogue it in the **SLIMEDEX** before it drifts away. The rarest arrive wrapped in colours that
> should not exist. And the rarest of all, the **DREAMDROP**, appears only on a blue moon: they say
> those are dreams that got lost on the way to someone.
>
> The happiness a slime radiates can be measured. And collected.
> One unit of it is called a **$SMILE**.

### 2.2 The animated site title

```
        ✦ ぷにぷに ✦
   P I X E L S L I M E
      PUNIPUNI PARADISE
```

Treatment: every letter is an independent sprite that **bounces on a stagger** (squash & stretch), with
a **goo drip** running off the S, looping **sparkle particles**, and a **wobble on hover**. The
`PUNIPUNI PARADISE` subtitle types itself out. On **MYTHIC** days the whole title shifts to an animated
rainbow foil.

### 2.3 Site sections (product vocabulary)

| Section | Product name | Purpose |
|---|---|---|
| Home | **TODAY'S BLOOM** — 今日のスライム | The card of the day, revealed with ceremony |
| Gallery | **SLIMEDEX** | Every card, filtered by type / rarity / date |
| Detail | **SLIME PROFILE** | Big card, animated stats, lore, provenance |
| Explainer | **PUNI LAB** | How rarities, types and stats work |
| Blockchain | **SMILE BANK** | $SMILE token, mints, wallet (phase 2) |
| Account | **KEEPER CARD** | Optional wallet connect (phase 2) — anonymous by default |

### 2.4 Rarities

| # | Rarity | House name | Roll weight | Visual treatment |
|---:|---|---|---:|---|
| 0 | `COMMON` | **Puddle** | 45 % | plain wooden frame, soft palette |
| 1 | `UNCOMMON` | **Dewdrop** | 27 % | silver frame, light halo |
| 2 | `RARE` | **Prism** | 17 % | blue frame, prismatic highlights |
| 3 | `EPIC` | **Aurora** | 8 % | gold/violet frame, gem, sparkle *(= Mochibo)* |
| 4 | `LEGENDARY` | **Starlight** | 2.5 % | animated celestial frame, constellation background |
| 5 | `MYTHIC` | **Dreamdrop** | 0.5 % | oversized, rainbow foil, frame that overflows the card |

> The rarity roll happens **in code** (seeded weighted random), **never left to the LLM** — that is the
> only way to get a genuinely controlled and auditable distribution.
> Anti-frustration guarantee: **no card ≥ RARE for 14 days → the next roll is forced to ≥ RARE** (pity timer).

### 2.5 Types (16 → fits in 4 bits)

`FAIRY` · `FOREST` · `WATER` · `EMBER` · `STORM` · `STONE` · `SUGAR` · `GHOST`
`METAL` · `COSMIC` · `BLOOM` · `FROST` · `SLUDGE` · `BEAM` · `PAPER` · `DREAM`

### 2.6 Palette & typography

| Role | Value |
|---|---|
| Cream (background) | `#FFF6E5` |
| Bubblegum | `#FF8FC5` |
| Mint | `#7FE3C0` |
| Sky | `#8FD3FF` |
| Grape | `#8B6FE8` |
| Sunbeam | `#FFD86B` |
| Ink (text) | `#2B1B4A` |
| Coral (accent/CTA) | `#FF7A59` |

Fonts, all open-licence (OFL): **Press Start 2P** for pixel headings, **M PLUS Rounded 1c** for body
copy (round, kawaii, handles Japanese), **Silkscreen** for stat labels.

Animation principles: squash & stretch everywhere, easing `cubic-bezier(.34,1.56,.64,1)` (slight
overshoot), nothing longer than 600 ms, and **strict `prefers-reduced-motion` support**.

---

## 3. Target Azure architecture

Everything lands in **`FGI-ASMDBPIXELSMILES` / swedencentral** — the same region as the model, so
image-generation latency stays minimal.

```
   Anyone on the internet — no sign-in, no account, nothing to log into
                                    │
   Browser ────HTTPS───►  ┌─────────▼─────────────────────────────────────────────────┐
                          │  ca-pixelslime-api   (Azure Container App, 0→3 replicas)   │
                          │  ─ FastAPI (Python 3.12)                                   │
                          │  ─ ALSO serves the built React SPA → one origin, zero CORS  │
                          └───┬───────────────┬───────────────┬───────────────┬────────┘
                              │               │               │               │
             Managed identity │               │               │               │
             (user-assigned)  │               │               │               │
                              ▼               ▼               ▼               ▼
                 ┌────────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐
                 │ kv-pixelslime  │  │ stpixelslime │  │ appi/log   │  │  asmdb.cloud     │
                 │ (Key Vault)    │  │ (Blob: PNG,  │  │ (App       │  │  /db/evedvw2…    │
                 │ asmdb-token 🔑 │  │  thumbs)     │  │  Insights) │  │  Bearer token    │
                 └────────────────┘  └──────────────┘  └────────────┘  └──────────────────┘
                              │
                              │ Cognitive Services User (cross-RG)
                              ▼
                 ┌───────────────────────────────────────────┐
                 │ fgi (RG FGI-AI) — gpt-image-2, gpt-5.6-sol │
                 └───────────────────────────────────────────┘

   ┌────────────────────────────────────────────────────────────────────┐
   │  caj-pixelslime-daily  (Container Apps Job, cron "0 8,9 * * *" UTC)  │
   │  same image as the API, different entrypoint → generates the card   │
   │  → publishes at 10:00 Europe/Paris, all year (see §3.4)             │
   └────────────────────────────────────────────────────────────────────┘
```

### 3.1 Resources to create

| Resource | Name | SKU / setting | Purpose |
|---|---|---|---|
| User-assigned managed identity | `id-pixelslime` | — | **The platform's single identity** |
| Key Vault | `kv-pixelslime-<suffix>` | Standard, **RBAC**, soft-delete + purge protection | `asmdb-bearer-token` (you drop it in), later chain keys |
| Storage account | `stpixelslime<suffix>` | Standard_LRS, TLS 1.2, **public blob access disabled** | containers `cards`, `thumbs`, `assets` |
| Container registry | `crpixelslime<suffix>` | Basic, admin user disabled | application image |
| Log Analytics | `log-pixelslime` | PerGB2018, 30-day retention | logs |
| Application Insights | `appi-pixelslime` | workspace-based | traces, metrics, alerts |
| Container Apps environment | `cae-pixelslime` | Consumption | hosting |
| Container App | `ca-pixelslime-api` | min 0 / max 3, external ingress, **public, no auth** | API + site |
| Container Apps Job | `caj-pixelslime-daily` | schedule `0 8,9 * * *` UTC, 1 retry | daily generation at **10:00 Europe/Paris** |

**RBAC assignments for `id-pixelslime`** (all in Bicep, no manual clicking):

| Role | Scope |
|---|---|
| `Key Vault Secrets User` | `kv-pixelslime-*` |
| `Storage Blob Data Contributor` | `stpixelslime*` |
| `AcrPull` | `crpixelslime*` |
| **`Cognitive Services User`** | `/subscriptions/49d5e158…/resourceGroups/FGI-AI/providers/Microsoft.CognitiveServices/accounts/fgi` ← **cross-RG; this is what replaces the disabled API key** |
| `Monitoring Metrics Publisher` | `appi-pixelslime` |

### 3.2 Why these choices

- **One Container App serves both the API and the SPA.** One origin means **asmDB's missing CORS stops
  being a problem by construction**, and there is a single deployment.
  (Rejected alternative: Static Web Apps + a separate API = two things to deploy and keep in sync.)
- **Container Apps over App Service**: scale-to-zero (near-zero cost overnight), **native cron Jobs**
  that reuse the same image, and a much lower idle cost.
- **A separate Job rather than an in-process scheduler**: if the API scales to 0 or to 3 replicas, an
  in-process `APScheduler` would produce 0 or 3 cards. A cron Job guarantees **exactly one run**.
- **No secrets in code or in plaintext environment variables**: Key Vault + managed identity.

### 3.3 Estimated monthly cost

| Item | Estimate |
|---|---|
| Container Apps (scale-to-zero, low internal traffic) | ~€5–12 |
| Container Apps Job (30 runs × ~3 min) | < €1 |
| Storage (365 PNGs ≈ 800 MB/year + thumbs) | ~€1 |
| ACR Basic | ~€4 |
| Log Analytics + App Insights (sampled) | ~€3–6 |
| Key Vault | < €1 |
| **gpt-image-2**: one 1024×1536 image/day | per your model pricing — the dominant line item |
| asmDB | Free tier (€0) |
| **Total excluding AI** | **≈ €15–25 / month** |

### 3.4 Publishing at 10:00 Paris, all year

The daily card lands at **10:00 Europe/Paris**. That is slightly less trivial than it sounds, because
**Container Apps Jobs cron expressions are evaluated in UTC only** — there is no timezone setting. Paris
is `UTC+2` in summer (CEST) and `UTC+1` in winter (CET), so a single fixed UTC hour drifts by an hour
twice a year:

| Naive cron | Summer (CEST) | Winter (CET) |
|---|---|---|
| `0 8 * * *` UTC | ✅ 10:00 Paris | ❌ 09:00 Paris |
| `0 9 * * *` UTC | ❌ 11:00 Paris | ✅ 10:00 Paris |

So the job is scheduled at **both** hours — `0 8,9 * * *` — and the first thing it does is check the
local wall clock:

```python
if datetime.now(ZoneInfo("Europe/Paris")).hour != 10:
    log.info("not 10:00 in Paris yet — standing down")
    return
```

Exactly one of the two runs passes that check on any given day. The other exits in under a second and
costs essentially nothing. And because the job is **already idempotent on the mint date**
([§5](#5-the-ai-generation-pipeline)), even a double-fire could not produce two cards — the guard is
about *punctuality*, not correctness.

The countdown on the home page (`"next slime in 07:12:44"`) is computed against the same
`Europe/Paris` 10:00 boundary, so the site and the job never disagree.

---

## 4. The core problem: fitting a card into asmDB

This is the part that has to be rigorous, because your starting note contains one assumption that does
not hold and one observation I can confirm.

### 4.1 The real budget, column by column

What is available **per row**:

| Field | Raw capacity | Usable for payload? |
|---|---|---|
| `id` (u64) | 8 B | ✅ but it is our **addressing scheme** (see 4.3) |
| `value` (i64) | 8 B | ✅ and it is the **only `RANGE`-filterable column** → far too valuable to spend on payload |
| `tag` (39 B) | 39 B | ✅ but text, no spaces; used as a **partition key** and as a `FIND` target |
| `content` (175 B) | 175 B | ✅ **the actual payload** — but UTF-8 text with no `\0 \r \n` |

### 4.2 Choosing the text envelope: **Z85**

Since `content` must be text, the binary has to be encoded. The options:

| Encoding | Ratio | Binary bytes inside 175 characters | Verdict |
|---|---|---:|---|
| Raw JSON (v0) | 1 char = 1 B | ~175, but the JSON alone is 700+ B | ✗ |
| Hex | 2 chars / B | **87 B** | ✗ wasteful |
| Base64 | 4 chars / 3 B | **131 B** | ~ acceptable |
| **Z85** (ZeroMQ alphabet, 85 symbols) | 5 chars / 4 B | **140 B** | ✅ **chosen** |
| Base91 | ~ | ~142 B | ✗ +2 B for a lot of complexity |

**Z85 wins**: +7 % capacity over base64, and its alphabet
(`0-9 a-z A-Z . - : + = ^ ! / * ? & < > ( ) [ ] { } @ % $ #`) contains **no backslash, no space, no tab
and no quote** — so it cannot collide with the engine's internal TSV escaping nor with the 511-byte
command-line limit. Implementation: ~40 lines plus exhaustive property-based round-trip tests.

> 📌 **Effective capacity: 140 binary bytes per asmDB row.**

### 4.3 Why one row is not enough — and the fix

Take your own Mochibo example and drop the 23 bytes of unused reserve:

```
header + numeric fields      16 B
DEFLATE-compressed text     125 B
CRC                           2 B
                           ──────
total                       143 B   >   140 B available   ✗
```

**Your example already does not fit**, by 3 bytes. And you said it yourself: *"no compressor can
guarantee that arbitrarily long text will always fit."* A design that breaks on a slightly wordy
description is not acceptable for an unattended daily job.

**Chosen solution — the `PSC-1` codec: one continuous byte stream, chunked across rows.**

A card is not "a row": it is **a small group of contiguous, O(1)-addressable rows**.

```
row id  =  serial × 16 + part          (part ∈ 0..15)
```

| `part` | Contents |
|---:|---|
| `0` | PSC-1 header + start of the compressed stream |
| `1..3` | Continuation of the compressed stream (only when needed) |
| `8` | **Blockchain anchor** (tx hash, tokenId, block) — phase 2 |
| `9..15` | Reserved for future extensions |

- `SELECT` by id is **O(1)** in the engine → reading a card is 1–2 GETs, never a scan.
- 393,216 available rows ÷ ~2 rows per card ≈ **190,000 cards**. At one card per day that is ~520 years
  of headroom, so chunking costs us nothing.

### 4.4 The `PSC-1` binary format

**Fixed header — 32 bytes:**

| Off | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 1 | `magic` | `0x50` (`'P'`) |
| 1 | 1 | `version` | `0x01`, also pins the dictionary version |
| 2 | 2 | `serial` | `u16` — card number (1..65535) |
| 4 | 2 | `total_len` | `u16` — total stream length, so the reader knows how many rows to fetch |
| 6 | 1 | `level` | `u8` |
| 7 | 1 | `rarity:3 / type:4 / shiny:1` | bitfield |
| 8 | 2 | `height_mm` | `u16` |
| 10 | 2 | `weight_g` | `u16` |
| 12 | 4 | `strength`, `endurance`, `agility`, `happiness` | 4 × `u8` |
| 16 | 4 | `art_id`, `style_id`, `frame_id`, `background_id` | 4 × `u8` |
| 20 | 2 | `biome_id`, `mood_id` | 2 × `u8` |
| 22 | 2 | `flags` | companion / accessory / minted / verified… |
| 24 | 2 | `mint_day` | `u16` — days since 2026-01-01 |
| 26 | 4 | `art_sha` | first 4 bytes of the PNG's SHA-256 (integrity + on-chain provenance) |
| 30 | 2 | `crc16` | integrity check over the whole stream |

**Body — compressed text.** The five text fields (`name`, `personality`, `power_name`, `power_desc`,
`quote`) are joined with a `0x1F` separator and compressed with **raw DEFLATE (`wbits=-15`) using a
preset dictionary** (`zlib.compressobj(zdict=…)`).

> 🔑 **The preset dictionary is where the real gain is.** A ~2 KB dictionary trained on PixelSlime
> vocabulary ("Loves cozy places", "healing allies over time", "Sweet and cuddly", the type names, the
> recurring sentence shapes) ships in the repo and is pinned by the header version byte. On short
> strings DEFLATE alone is nearly useless; with a dictionary we typically see **−35 % to −50 %**.
> Target: **the median card fits in a single row.**

**Projected budget** for a typical card:

```
header                                   32 B
DEFLATE text with dictionary        ~70–110 B
                                    ─────────
total                              ~102–142 B   →  1 row (2 for a chatty card)
```

### 4.5 Guardrails — what makes this unbreakable

1. **Maximum lengths enforced at the source** (in the LLM's JSON schema): `name` ≤ 18,
   `power_name` ≤ 20, `personality` ≤ 90, `power_desc` ≤ 90, `quote` ≤ 40 characters. Your own
   conclusion, applied.
2. **Validation before writing**: if the stream exceeds 4 rows (560 B), encoding fails *loudly* and the
   generator re-prompts the LLM asking for shorter text. Never a silent truncation.
3. **Mandatory round-trip**: after every write the card is **read back from asmDB, decoded and compared**
   to the source JSON. Any divergence → alert + rollback.
4. **`crc16`** in the header detects a missing or corrupted row.
5. **Frozen test vectors** (`contracts/psc1-vectors.json`), **including Mochibo**, lock the format
   between agents and catch any codec regression.

### 4.6 Using `value` and `tag` — building the index asmDB doesn't have

asmDB has **no secondary index**, and `FIND`/`RANGE` are full scans. So we build an index out of the
only two columns that can carry one:

| Row | `value` | `tag` |
|---|---|---|
| `part = 0` (header) | **mint date as `YYYYMMDD`** (e.g. `20260728`) — **positive** | `psc.<serial>.0` |
| `part ≥ 1` | **`-(serial×16+part)`** — **always negative** | `psc.<serial>.<part>` |

Direct consequences, with no application-side scanning:

- **Card of the day** → `GET /v1/range?lo=20260728&hi=20260728` → one row, the header.
- **All cards in a month or a year** → `RANGE` over the span, paginated.
- **Continuation rows never pollute those results**, because their `value` is negative and any `lo ≥ 0`
  excludes them. That small detail is what makes the index actually usable.
- `FIND?q=psc.42.` recovers every row of a card if we ever lose the serial.

**And on top: a backend cache.** The API keeps an in-memory index (`serial → metadata`), mirrored to an
`index.json` blob, rebuilt at startup and updated on every new card. The gallery therefore **never**
hits asmDB on the hot path. asmDB stays the **source of truth**; `index.json` is a rebuildable projection.

### 4.7 What about the image?

The PNG is ~2 MB — it obviously does not go in a 175-byte row. It goes to **Blob Storage**, at a
**deterministic path derived from the serial**:

```
cards/PS-00042.png      (1024×1536, alpha)
thumbs/PS-00042.webp    (512×768, for the gallery)
```

**Cost in asmDB: 0 bytes.** No URL is stored — it is recomputed. Only 4 bytes of SHA-256 are kept in the
header, to prove the blob matches the card.

---

## 5. The AI generation pipeline

The guiding principle: **data first, image second.** Generating the image and then OCR-ing stats out of
it would be fragile. Instead we generate a structured JSON, ask `gpt-image-2` to **paint exactly that
JSON**, then **verify** the image agrees with it.

```
┌─ 1. ROLL ────────────────────────────────────────────────────────────┐
│ In code (not the LLM): weighted rarity + pity timer, biome, mood,     │
│ companion, deterministic seed = f(date). Fully reproducible.          │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌─ 2. METADATA ── gpt-5.6-sol + Structured Outputs (JSON Schema) ──────┐
│ Input: your master prompt + the roll + the list of names already used │
│ (dedup, read from the index cache).                                   │
│ Output: the card JSON, length-constrained, 100 % English.             │
│ Validation: Pydantic + a trial PSC-1 encode. On failure → 2 retries.  │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌─ 3. IMAGE ── gpt-image-2 ────────────────────────────────────────────┐
│ POST /openai/v1/images/edits   (multipart — CONFIRMED WORKING;        │
│                                 `image` is rejected on /generations)  │
│   image=assets/template/mochibo.png   ← your reference card           │
│   size=1024x1536  background=transparent  quality=high  format=png    │
│   prompt = style template + THE CARD JSON, field by field             │
│ Fallback: /generations with a very detailed style prompt.             │
│ Retry: exponential backoff honouring the Retry-After header (429).    │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌─ 4. VERIFICATION ── vision model ────────────────────────────────────┐
│ Read the rendered card back and compare name / level / rarity / stats │
│ against the source JSON. This is the "extraction model" you mentioned. │
│ Plus technical checks: alpha channel present, corners genuinely       │
│ transparent, correct dimensions, portrait orientation.                │
│ Mismatch → one more image attempt, then alert.                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌─ 5. POST-PROCESSING ── Pillow ───────────────────────────────────────┐
│ alpha trim, 512×768 WebP thumbnail, SHA-256, dominant palette         │
│ (reused by the frontend to tint the UI in the card's own colours).    │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌─ 6. PERSISTENCE ─────────────────────────────────────────────────────┐
│ Blob (PNG + WebP) → PSC-1 encode → POST /v1/rows (header + parts)     │
│ → READ BACK + decode + compare (round-trip)                           │
│ → refresh index.json → (phase 2) mint on-chain                        │
└──────────────────────────────────────────────────────────────────────┘
```

**Idempotency.** The business key is the date. The job starts with
`GET /v1/range?lo=<today>&hi=<today>`: if a card already exists it stops. A double run (Azure retry,
redeploy) therefore cannot create two cards on the same day.

### 5.1 The master prompt (your prompt, translated to English)

Your original French brief is the product intent and is kept verbatim in the repo for reference, but the
model is driven by this English version. It lives in `backend/app/ai/prompts/master_prompt.md`, is
**versioned**, and its version id is logged with every card so a style drift can still be explained six
months from now.

```text
PIXEL SLIME — TRADING CARD MASTER PROMPT  (v1)

Generate ONE unique Pixel Slime: an adorable, super fun little creature,
drawn in rich, detailed PIXEL ART.

── FORMAT ──────────────────────────────────────────────────────────────
· Present it as a collectible trading card, in the spirit of a Pokémon
  card or equivalent.
· The card is VERTICAL (portrait).
· IMPORTANT: everything OUTSIDE the card's rounded border must be FULLY
  TRANSPARENT. No backdrop, no outer drop shadow, no checkerboard, no
  white box — real alpha transparency.

── THE SLIME ───────────────────────────────────────────────────────────
· The slime's shape is RANDOM and may look completely different from the
  reference image. The reference defines the CARD STYLE and LAYOUT, not
  the creature.
· It may take different silhouettes, wear accessories, and show a
  different mood.
· It may be joined by a small animal companion that grants it a boost or
  a power.

── THE SCENE ───────────────────────────────────────────────────────────
· The slime is unique and placed in a RANDOM situational environment:
  out in nature, inside a house, a cosy bedroom, a rainy street, a
  workshop, a library at dusk — imagine one. Keep it fun.

── THE CARD MUST SHOW (all text in ENGLISH) ────────────────────────────
    NAME · TYPE · LEVEL · RARITY · HEIGHT · WEIGHT
    PERSONALITY · POWER (name + description)
    STRENGTH · ENDURANCE · AGILITY · HAPPINESS
    a short spoken quote from the slime, and its ID

── RARITY ──────────────────────────────────────────────────────────────
· A level and a rarity must be generated.
· The rarer the card, the more exceptional its colours and its frame.

── NAMING ──────────────────────────────────────────────────────────────
· Be imaginative with slime names — random, but fun.
```

At runtime the job appends the exact values drawn in steps 1–2 (name, level, rarity, type, stats, biome,
companion, power, quote), so the model is never left to invent numbers the database will disagree with.

### 5.2 A note on the reference image

`mochibo.png` is the **style reference** handed to `/images/edits`. Worth knowing before we use it:

> I inspected the file. It is **`RGB`, 1024×1536, with no alpha channel at all** — the "transparent"
> area around the card is a **checkerboard pattern painted into the pixels** (8-px cells alternating
> `#E6E7E6` / `#FDFDFD`).

The prompt is what enforces transparency, so this is not a blocker. But feeding a picture of a
checkerboard to an image model as a style reference is asking it to **paint a checkerboard**. So W0
ships a cleaned template: flood-fill the checkerboard from the corners, convert it to a true alpha
channel, and store the result as `assets/template/mochibo.png` (the original is kept alongside as
`mochibo-original.png`). Cheap to do, and it removes an entire class of weird output.

---

## 6. The web application

### 6.1 Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | **React 18 + TypeScript + Vite** | fast, mature animation ecosystem |
| Styling | **Tailwind CSS** + custom design tokens | quick visual iteration, consistency |
| Animation | **Framer Motion** + CSS keyframes + Canvas (particles) | delivers the "wow" you asked for |
| State / data | **TanStack Query** + Zustand | caching, revalidation, offline-friendly |
| Backend | **FastAPI (Python 3.12)** + uvicorn | native `struct`/`zlib` for the codec, first-class Azure SDKs, free OpenAPI |
| Testing | pytest + Vitest + Playwright | unit, component, E2E |

> Python on the backend is a deliberate choice: the PSC-1 codec (binary packing + dictionary DEFLATE)
> and image post-processing are *exactly* what `struct`, `zlib` and Pillow are for — and your
> `mochibo_card_codec.py` prototype is already in that language.

### 6.2 API surface

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/health` | liveness |
| `GET` | `/api/cards/today` | today's card + seconds until the next one |
| `GET` | `/api/cards?page=&type=&rarity=&sort=` | paginated SLIMEDEX (served from cache) |
| `GET` | `/api/cards/{serial}` | full decoded card |
| `GET` | `/api/cards/{serial}/image` | PNG proxy, `Cache-Control: immutable` |
| `GET` | `/api/cards/{serial}/thumb` | WebP thumbnail proxy |
| `GET` | `/api/cards/{serial}/raw` | the raw PSC-1 in Z85 plus its decoding — **the "provenance" page, very geeky, very cool** |
| `GET` | `/api/stats` | global counters: total, rarity distribution, streak |
| `POST` | `/api/admin/generate` | manual trigger (guarded by a Key Vault admin token header, off by default) |
| `GET` | `/api/nft/{serial}` | ERC-721 metadata (phase 2) |

Images go through a **backend proxy** (the blob container is private, no anonymous access) with a long
cache header.

### 6.3 The screens

**① TODAY'S BLOOM (home)** — Animated title. Centre stage, today's card **face down**: a pulsing pixel
card back. Click → **3D flip**, particle burst, the card reveals itself, stat bars fill in a cascade, a
soft "puni!" sound (muted by default). The background adopts the card's dominant colours. If the rarity
is ≥ EPIC: confetti and a gentle screen shake. A live countdown reads "next slime in 07:12:44". A
ribbon shows "✦ DAY 42 ✦" and the collection streak.

**② SLIMEDEX (gallery)** — A grid of thumbnails that float gently on a stagger. Filters by type
(coloured pills), rarity, and month. Search by name. Cards this visitor has not opened yet appear as
dark silhouettes with a "???" — a Pokédex-style discovery mechanic, tracked purely in **`localStorage`**
(no account, nothing sent to the server). On hover the card lifts and tilts toward the pointer
(parallax/holo effect) and glows according to rarity.

**③ SLIME PROFILE (detail)** — The card at full size with a holographic effect driven by pointer or
gyroscope. Beside it: an animated stat radar, lore, biome, companion, birth date, serial number, the
blockchain badge (phase 2), and a "see the 175 bytes" link to the provenance page.

**④ PUNI LAB** — Explains rarities, types and stats, with little slimes demonstrating in animation.

**⑤ SMILE BANK** (phase 2) — $SMILE balance, mint history, block-explorer links.

**⑥ The details that sell it** — A mascot slime wanders across the bottom of the screen now and then.
The cursor leaves a pixel trail. A Konami code unlocks a cosmetic "secret" slime. Dark mode is
**MOONLIT PUNIVERSE** (cool palette, fireflies).

### 6.4 Accessibility & performance

AA contrast on all text, full keyboard navigation, `prefers-reduced-motion` honoured (animations degrade
to fades), `loading="lazy"` + `srcset` on images, a budget of < 200 KB gzipped JS excluding fonts, and
LCP < 2 s.

---

## 7. Security (public site)

**There is no sign-in.** The site is fully public: anyone can browse the SLIMEDEX, open the daily card
and read every stat. No Entra app registration, no Easy Auth, no login wall, no user database.

That decision moves the entire security burden to one place: **the backend is the only thing that holds
credentials, and it never hands them out.**

| Concern | How it is handled |
|---|---|
| **asmDB bearer token** | Stored in **Key Vault**, read at startup through the **managed identity**, held in memory only. Never logged, never in an env var in plaintext, never sent to the browser. Since asmDB sends no CORS headers, the browser *cannot* reach it even if it wanted to. |
| **AI models** | Called **only** from the backend and the daily job, authenticated with the **user-assigned managed identity** (`Cognitive Services User` on account `fgi`). No API key exists, because key auth is disabled. The browser never touches the model endpoint. |
| **Blob Storage** | Public blob access **disabled**. Images are served through the backend proxy with long cache headers. |
| **Write paths** | The public API is **read-only**. The only writer is the Container Apps Job, which runs on the same identity but is not reachable from the internet. |
| **Manual trigger** | `POST /api/admin/generate` is protected by a **Key Vault-held admin token** sent as a header — not a user login. It is off by default and intended for you and the runbook. |
| **Abuse / cost** | Rate limiting per IP on the API, aggressive caching (the gallery is served from the in-memory index, not asmDB), and a hard daily cap on image generation in the job. A public site cannot make us spend more on AI, because **visitors cannot trigger generation at all**. |
| **Content** | Everything is generated by us, on a fixed prompt; there is no user-supplied input anywhere in the system, so no injection surface into the prompt. |
| **Transport** | HTTPS only, strict CSP, standard security headers, Dependabot + `pip-audit`. |
| **Token rotation** | The asmDB token is readable only once; the rotation procedure (`rotate-token` → `rotate-token/commit`) is documented in `docs/RUNBOOK.md`. |

> The pleasant consequence of dropping auth: **there is no personal data in this system at all.**
> Per-visitor state (which slimes you've "discovered", your reduced-motion preference, dark mode) lives
> in **`localStorage`** in the browser. Nothing about a visitor is ever sent to, or stored on, the server.

---

## 8. Phase 2: blockchain & the $SMILE token

Designed **now** (the hooks are reserved in the format and the id scheme), **shipped after** the MVP.

### 8.1 The problem you spotted

You put your finger on exactly the right hole:

> *"publishing cards costs $SMILE — but we haven't distributed any $SMILE yet."*

There are really **two** problems hiding in there, and they have different answers.

**Problem 1 — the bootstrap.** If publishing costs $SMILE and no $SMILE exists, nothing can ever be
published. Every token economy has this, and every one of them solves it the same way: a **genesis
event**. The interesting question is not *whether* to pre-mint, it's *who holds it and what depletes it*.

**Problem 2 — who is "the user"?** We just made the site **public with no login**. There are no accounts,
so there is no ledger of who owns what. A naive design would give $SMILE to "users" who do not exist.

There is also a trap worth naming: if the same wallet both **pays** the fee and **receives** the reward,
the fee is theatre. Money moves from a pocket back into the same pocket and nothing is actually scarce.
**A fee is only real if the payer and the earner are different, and if the payer's purse is finite.**
That single constraint drives the whole design below.

### 8.2 Two different costs — don't confuse them

| | **Gas** | **The Bloom Fee** |
|---|---|---|
| What | Real network fee to write a transaction | An in-universe cost we invent |
| Paid in | MATIC | **$SMILE** |
| Who sets it | The chain | **Us** |
| Why it exists | Physics of the blockchain | **Game design** |
| On Amoy testnet | **Free** (faucet) | Whatever we decide |

Gas is unavoidable and tiny. The Bloom Fee is a **deliberate mechanic**, so it has to earn its place.

### 8.3 The economy: Genesis Rain → Bloom Burn → Claim Pool

The lore does the explaining, and the mechanics follow it exactly:

> Happiness cannot be created by decree. It has to be **felt** first.
> Before the first slime ever bloomed, the Great Pixel Rain left behind one finite puddle of
> happiness — **the Genesis Rain**. Every slime that condenses out of the sky **spends** a little of
> that original puddle. In exchange, the slime radiates happiness of its own — and that new happiness
> does not go back into the puddle. It goes **to the people who come and look at it**.

```
   ┌──────────────────────────┐
   │   GENESIS RAIN           │   one-time mint at deployment
   │   1,000,000 $SMILE       │   held by the TREASURY (Key Vault key)
   │   ── FINITE, NEVER       │
   │      REFILLED ──         │
   └───────────┬──────────────┘
               │  every daily bloom pays a
               │  BLOOM FEE of 100 $SMILE
               ▼
        ┌─────────────┐
        │   🔥 BURNED  │   destroyed forever — the Treasury genuinely shrinks
        └─────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │  Meanwhile, the card that just bloomed MINTS new $SMILE:      │
   │      yield = happiness × rarityMultiplier                     │
   │  …but NOT into the Treasury. Into a separate CLAIM POOL       │
   │  that the Treasury has no authority to spend.                 │
   └───────────┬──────────────────────────────────────────────────┘
               ▼
   ┌──────────────────────────┐
   │   CLAIM POOL             │  visitors claim from here, if they want to
   │                          │  (optional wallet connect — still no login)
   └───────────┬──────────────┘
               │  PHASE 3 sinks: adopt a slime, summon a bonus slime
               ▼
        ┌─────────────┐
        │   🔥 BURNED  │
        └─────────────┘
```

**Why this is not circular.** The Treasury pays the fee and the fee is *burned*. The yield is minted to
a *different* pool the Treasury cannot touch. So the Genesis Rain only ever goes **down**:

```
1,000,000 $SMILE  ÷  100 $SMILE per bloom  =  10,000 blooms  ≈  27 years of daily slimes
```

That number is a feature, not an accident. The site can display it as a live countdown —
**"GENESIS RAIN REMAINING: 998,400 $SMILE · 9,984 slimes left"** — and it is *true*. Scarcity you can
verify on a block explorer is far more interesting than scarcity you assert in marketing copy.

### 8.4 Who holds the tokens when there are no accounts

This is the elegant part of dropping login: **identity becomes optional and lives on-chain, not in Entra.**

| Visitor | What they get |
|---|---|
| **Anonymous** (the default, and 99 % of traffic) | The complete site. Every card, every stat, every animation, the whole SLIMEDEX. **Nothing is gated.** |
| **Connects a wallet** (opt-in, one click, no account created) | Can additionally **claim $SMILE** and later **adopt** slimes. |

Claiming uses the standard, boring, well-understood pattern: the backend signs an **EIP-712 voucher**
`(wallet, serial, amount, nonce)` with the Key Vault key, and the contract verifies that signature before
paying out of the Claim Pool. No balance is ever stored on our side — the chain is the ledger.

Sybil resistance is deliberately *light*: a per-wallet daily cap, a per-card cap, and IP rate limiting on
the voucher endpoint. This is a fun internal collectible, not a financial product, and I would rather say
that plainly than pretend otherwise.

### 8.5 Where the NFTs live

Each daily card is minted as an **ERC-721 into the SLIMEDEX Vault** (the Treasury). Cards are not
airdropped to anyone, because there is nobody to airdrop them to.

That gives Phase 3 its purpose: **adoption**. A visitor spends $SMILE to have a slime transfer out of the
Vault into their wallet. That is the real sink, and it is what finally gives $SMILE something to be *for*.

| Rarity | Adoption price | Bloom yield (happiness × mult) |
|---|---:|---:|
| COMMON · Puddle | 200 | × 1 |
| UNCOMMON · Dewdrop | 400 | × 2 |
| RARE · Prism | 900 | × 4 |
| EPIC · Aurora | 2,000 | × 8 |
| LEGENDARY · Starlight | 6,000 | × 20 |
| MYTHIC · Dreamdrop | 25,000 | × 100 |

Expected yield per bloom ≈ `75 happiness × 3.31 average multiplier ≈ 248 $SMILE/day`, against a
100 $SMILE burn — so the *claimable* supply grows ~90,000/year while the *Treasury* shrinks
monotonically. Every one of these numbers is a constructor parameter, tunable before deployment and
governed by a `PARAMS` role afterwards.

### 8.6 Ship it in three steps, not one

The economy is the risky part; the provenance is not. So they are decoupled:

| Step | What ships | Depends on the economy? |
|---|---|---|
| **2a · ANCHOR** | `PixelSlimeCard` ERC-721 only. Each card's PSC-1 bytes are hashed with keccak256 and minted to the Vault. The "⛓️ ON-CHAIN" badge goes live. Cost: gas only. | ❌ **No token at all.** Pure provenance. |
| **2b · SMILE** | `SmileToken` + Genesis Rain + Bloom Fee burn + Claim Pool + wallet connect. | ✅ |
| **3 · ADOPT** | Adoption, bonus-slime summoning, the $SMILE sinks that close the loop. | ✅ |

**Step 2a is worth doing on its own**, and it is genuinely useful: it turns the 175-byte constraint from
a limitation into the product's best feature. The compact PSC-1 payload becomes the **canonical thing
that gets hashed** — the chain proves a given slime existed exactly as it is, on that date, without
duplicating a single byte of it.

### 8.7 Chain choice

**Polygon PoS** — **Amoy** testnet first, mainnet only if you want it.
Rationale: EVM (the richest open-source ecosystem), negligible fees, low energy footprint (PoS), and
fully open-source tooling: **Foundry**, **OpenZeppelin Contracts** (MIT), **web3.py**.
Alternatives considered: Base (also a solid L2); Solana (excellent for NFTs, but a separate Rust stack
and more expensive in skills here).

On Amoy the whole economy runs on **free faucet MATIC**, which means we can operate the full loop for as
long as we like before deciding whether real money is ever involved.

### 8.8 The contracts (Solidity, OpenZeppelin)

| Contract | Standard | Purpose |
|---|---|---|
| `SmileToken.sol` | **ERC-20** `$SMILE` | `ERC20Burnable` + `AccessControl`. `GENESIS_RAIN` minted once to the Treasury in the constructor, then **the Treasury's minter role is renounced** — so the puddle provably cannot be refilled. |
| `PixelSlimeCard.sol` | **ERC-721** | `tokenId = serial`. Stores `bytes32 cardHash = keccak256(PSC-1 stream)`. `tokenURI` → `/api/nft/{serial}`. Minted to the Vault. |
| `ClaimPool.sol` | — | Holds bloom yield. Pays out against **EIP-712 vouchers** signed by the Key Vault key. Per-wallet and per-card caps enforced on-chain. |
| `SlimeAdoption.sol` | — | Phase 3. Burns $SMILE, transfers the NFT out of the Vault. |

### 8.9 Signing transactions — without ever exposing a private key

Azure Key Vault supports EC keys on curve **P-256K (secp256k1)** — precisely Ethereum's curve. The
Treasury key is created **inside Key Vault**, non-exportable, and transactions are signed through the Key
Vault API using the managed identity (`Key Vault Crypto User`). **The private key never leaves the HSM
and exists nowhere in the code, the environment, or the logs.**
*(Simpler fallback if needed: private key as a Key Vault secret — weaker, but acceptable on testnet.)*

### 8.10 Pipeline integration

After the asmDB write, the job calls `mintCard(serial, cardHash, tokenURI)`. The transaction hash,
`tokenId` and block number are written to the card's **`part = 8` row** — which is exactly why that slot
was reserved in [§4.3](#43-why-one-row-is-not-enough--and-the-fix).

Minting is **decoupled and replayable**: if the chain is unavailable the card still exists in asmDB, and
a catch-up job mints the backlog. **The blockchain must never block the card of the day.**

### 8.11 Decentralised storage (option)

Pin the PNGs to **IPFS** (via an open-source pinning service) and point `tokenURI` there, so the NFT
survives the app disappearing. Planned as an opt-in, not a dependency.

---

## 9. Multi-agent development plan

The split follows one rule: **you don't parallelise code, you parallelise contracts.** A short W0
workstream freezes the interfaces; after that, eight workstreams run in parallel without colliding.

### 9.1 Dependency graph

```
                        ┌──────────────────────────────┐
                        │  W0 · CONTRACTS & SKELETON   │   (blocking, short)
                        │  schemas, OpenAPI, tokens,   │
                        │  test vectors, Dockerfile    │
                        └───────────────┬──────────────┘
        ┌───────────┬───────────┬───────┴────┬───────────┬───────────┐
        ▼           ▼           ▼            ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌─────────┐  ┌────────┐  ┌────────┐  ┌────────┐
   │W1 INFRA│  │W2 CODEC│  │W3 ASMDB │  │W4  AI  │  │W5 DSGN │  │W6 FRONT│
   │ Bicep  │  │ PSC-1  │  │ client  │  │pipeline│  │ system │  │ React  │
   └───┬────┘  └───┬────┘  └────┬────┘  └───┬────┘  └───┬────┘  └───┬────┘
       │           └──────┬─────┘           │           └───────────┘
       │                  ▼                 │                 │
       │           ┌─────────────┐          │                 │
       └──────────►│ W7 BACKEND  │◄─────────┘                 │
                   │ FastAPI     │                            │
                   └──────┬──────┘                            │
                          ├────────────────────────────────────┘
                          ▼
                   ┌─────────────┐        ┌──────────────┐
                   │ W8 DAILY JOB│        │ W9 CHAIN     │ (phase 2, independent)
                   │             │        │ $SMILE       │
                   └──────┬──────┘        └──────────────┘
                          ▼
                   ┌─────────────┐
                   │ W10 QA / E2E│
                   └─────────────┘
```

### 9.2 The workstreams

| # | Workstream | Branch | Exclusive scope (no other agent touches it) | Depends on | Done when… |
|---|---|---|---|---|---|
| **W0** | **Contracts & skeleton** | `feat/w0-contracts` | `contracts/`, `docs/`, `Dockerfile`, `pyproject.toml`, `package.json`, CI | — | JSON schemas, `openapi.yaml`, PSC-1 vectors (incl. Mochibo), design tokens, green empty CI |
| **W1** | **Infrastructure** | `feat/w1-infra` | `infra/` | W0 | `az deployment group create` builds **the entire RG from scratch**, RBAC included; idempotent; `make infra` documented |
| **W2** | **PSC-1 codec** | `feat/w2-codec` | `backend/app/codec/` | W0 | Z85 + packing + dictionary DEFLATE + chunking. **All vectors pass**, 10,000-case round-trip fuzz, Mochibo fits in ≤ 2 rows |
| **W3** | **asmDB client** | `feat/w3-asmdb` | `backend/app/asmdb/` | W0 | CRUD + `find` + `range` + pagination + cold-start retry + backoff. Tests against a **fake server** plus one real integration test |
| **W4** | **AI pipeline** | `feat/w4-ai` | `backend/app/ai/` | W0 | Rarity roll, structured metadata, image call (`/edits` **validated first**), vision verification, post-processing. AI responses recorded as cassettes so tests replay offline |
| **W5** | **Design system** | `feat/w5-design` | `frontend/src/design/`, `docs/mockup/` | W0 | Tokens, `<SlimeCard>`, `<StatBar>`, `<AnimatedTitle>`, sprites, keyframes, and keeping **the HTML mockup** current |
| **W6** | **Frontend** | `feat/w6-frontend` | `frontend/src/` (excluding `design/`) | W0, W5 | All five screens wired to an **API mock** generated from `openapi.yaml` — so it **does not wait for W7** |
| **W7** | **Backend API** | `feat/w7-backend` | `backend/app/api/`, `core/`, `storage/` | W2, W3, W4 | Every route, index cache, image proxy, rate limiting, health. OpenAPI contract matched exactly |
| **W8** | **Daily job** | `feat/w8-job` | `backend/app/jobs/` | W7 | Orchestration, date idempotency, round-trip verification, App Insights alerts, backlog catch-up |
| **W9** | **Blockchain** | `feat/w9-chain` | `chain/`, `backend/app/chain/` | W0 (+ W7 at the end) | **Step 2a first**: `PixelSlimeCard` ERC-721 + Key Vault secp256k1 signer + Amoy deployment + mint script, no token. Then 2b (`SmileToken`, Genesis Rain, burn, `ClaimPool`, EIP-712 vouchers) and 3 (`SlimeAdoption`). Foundry tests throughout |
| **W10** | **QA & E2E** | `feat/w10-qa` | `tests/e2e/` | W6, W7 | Playwright journeys, accessibility tests, performance budget, light load test |

### 9.3 The rules that make parallelism real

1. **One workstream = one exclusive directory.** Two agents never edit the same file. Merge conflicts
   become structurally impossible.
2. **W0 is blocking and must stay short.** Everything that crosses a boundary (card schema, OpenAPI,
   codec vectors, design tokens) is frozen there and versioned.
3. **Everyone builds against a fake neighbour.** W6 codes against an API mock generated from
   `openapi.yaml`; W7 codes against a fake asmDB; W4 codes against recorded HTTP cassettes. Nobody waits.
4. **The test vectors are the law.** `contracts/psc1-vectors.json` (with Mochibo in it) is the binding
   evidence shared by W2, W7 and W8.
5. **One Definition of Done for everyone**: unit tests green, lint/format clean, strict typing
   (mypy / TS `strict`), docs updated, no secrets, PR reviewed.
6. **Merge order**: W0 → W1/W2/W3/W4/W5 (any order) → W6/W7 → W8 → W10 → W9.

### 9.4 Suggested waves

| Wave | In parallel | Outcome |
|---|---|---|
| **Wave 0** | W0 alone | contracts frozen |
| **Wave 1** | W1 + W2 + W3 + W4 + W5 | **5 agents in parallel** — the bulk of the foundational work |
| **Wave 2** | W6 + W7 | 2 agents; W6 on mocks, W7 on wave-1 building blocks |
| **Wave 3** | W8 + W10 | integration & quality |
| **Wave 4** | W9 | blockchain, with no pressure on the MVP |

---

## 10. Repository layout

```
pixelslime/
├─ docs/
│  ├─ PLAN.md               ← this document
│  ├─ LORE.md               the universe, rarities, types, bestiary
│  ├─ CODEC.md              PSC-1 specification (normative)
│  ├─ INFRA.md              resources, RBAC, deployment procedure
│  ├─ RUNBOOK.md            operations: token rotation, backfill, incidents
│  ├─ AGENTS.md             workstream rules, DoD, merge order
│  └─ mockup/index.html     ← the static HTML mockup
├─ contracts/
│  ├─ card.schema.json      the card JSON (source of truth)
│  ├─ openapi.yaml          API contract
│  ├─ psc1-vectors.json     codec test vectors (including Mochibo)
│  └─ design-tokens.json    colours, spacing, type, durations
├─ infra/
│  ├─ main.bicep            + modules/ (identity, kv, storage, acr, aca, job, rbac)
│  └─ deploy.ps1
├─ backend/
│  └─ app/
│     ├─ api/     core/     codec/     asmdb/     ai/     storage/     jobs/     chain/
│     └─ tests/
├─ frontend/
│  └─ src/  design/  components/  pages/  hooks/  mocks/
├─ chain/                   Foundry: src/ test/ script/
├─ assets/
│  ├─ template/mochibo.png  the reference card
│  └─ psdict_v1.bin         the DEFLATE dictionary
├─ scripts/                 seed, backfill, export
└─ .github/workflows/       ci.yml, deploy.yml
```

---

## 11. Milestones

| Milestone | Contents | Verifiable success criterion |
|---|---|---|
| **M0 — Foundations** | W0 + W1 | `az deployment` builds the full RG; you drop the bearer into Key Vault; the app's `/health` responds |
| **M1 — The data fits** | W2 + W3 | Mochibo is **encoded, written to smilesdb, read back, decoded and byte-identical**. This is the real first "it works". |
| **M2 — The first card** | W4 | A brand-new card is generated end to end (metadata + transparent 1024×1536 image) and verified |
| **M3 — The site is alive** | W5 + W6 + W7 | The site is online and public, showing the daily card and the SLIMEDEX, with **3 seed slimes** in the database |
| **M4 — It runs itself** | W8 + W10 | The cron job has run three days straight unattended; E2E tests pass |
| **M5 — The chain** | W9 | **2a**: `PixelSlimeCard` deployed on Amoy, one card anchored, on-chain badge visible. **2b**: `$SMILE` + Genesis Rain live, first bloom burn visible on the explorer |

**The 3 seed slimes** you asked for: generated at M2/M3 with deliberately contrasting forced rarities, so
the gallery looks good on day one and every tier's rendering gets validated — one **COMMON**, one
**RARE**, one **LEGENDARY**. Mochibo (EPIC) is imported as reference card **PS-0001**.

---

## 12. Risks, costs and open decisions

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | `/images/edits` does not reproduce the template as faithfully as hoped | **Medium** *(downgraded — the endpoint is confirmed to accept the multipart template)* | Validate the visual result first thing in W4. Fallback: a very detailed style prompt on `/generations` (confirmed working) with `background=transparent`. Last-resort fallback: composite the frame in Pillow over a slime-only illustration — the most controllable option of all. |
| R2 | **gpt-image-2 quota = 2** → frequent 429s | **High** | Backoff honouring `Retry-After`, serialised queue, staggered seeding. **Request a quota increase.** |
| R3 | Generated text exceeds the byte budget | Medium | Length constraints in the schema + DEFLATE dictionary + chunking up to 4 rows + loud failure and regeneration |
| R4 | asmDB cold start (free tier sleeps) | Medium | `/health` warm-up before writes, retry on `instance_starting`, backend index cache |
| R5 | The model renders misspelled or unreadable text inside the image | Medium | Step 4 vision verification + regeneration; displayed stats always come from the JSON, which is the source of truth |
| R6 | Style drift across cards over months | Low | Versioned master prompt, pinned `style_id`, the reference card is always sent |
| R7 | Uncontrolled image cost | Low | 1 image/day, hard cap in the job, Azure budget alert |
| R8 | Loss of the asmDB bearer | Low | Rotation procedure documented in the runbook |
| R9 | The reference template has **no alpha channel** — its "transparency" is a painted checkerboard, which an image model may reproduce as literal art | **Low** *(already fixed)* | Solved: `scripts/clean_template.py` flood-fills the checkerboard into a real alpha channel. **Already run** — `assets/template/mochibo.png` is now RGBA, 17.8 % transparent, corner alpha 0. Original kept as `mochibo-original.png`. |
| R10 | The site is **public** — scraping, hotlinking, or traffic spikes | Low | Read-only API, in-memory index (asmDB is never hit on the hot path), per-IP rate limiting, cached image proxy, Container Apps max 3 replicas. **Visitors cannot trigger generation**, so traffic can never increase the AI bill. |
| R11 | $SMILE economy parameters turn out wrong after deployment | Medium | Ship **step 2a (anchor only, no token)** first. Genesis Rain is the one irreversible number — everything else sits behind a `PARAMS` role. Testnet-first means a full reset costs nothing. |

### Decisions I made (and that you can overrule)

1. **Python/FastAPI** on the backend rather than Node — for `struct`/`zlib`/Pillow and continuity with your prototype.
2. **Container Apps** rather than App Service — scale-to-zero and native cron Jobs.
3. **A single service** serving both API and site — eliminates the CORS problem entirely.
4. **Z85 + multi-row chunking** rather than a single row — because your own example does not fit (143 > 140).
5. **Metadata first, image second** — rather than OCR-ing stats out of the image.
6. **Polygon Amoy** to start the chain — free, EVM, open-source tooling.
7. **No login at all** (your call) — which also means **no personal data anywhere in the system**. Per-visitor state lives in `localStorage`.
8. **The Bloom Fee is burned from a finite Genesis Rain, while the yield mints to a separate Claim Pool** — so the fee is real rather than the Treasury paying itself. This is the answer to "we haven't distributed any $SMILE yet".
9. **Chain ships in three steps** — anchor-only, then the token, then adoption — so provenance is not held hostage by economics.

---

## 13. What I need from you before the GO

| # | Action | Why |
|---|---|---|
| 1 | **GO or adjustments** on this plan and on the mockup `docs/mockup/index.html` | — |
| 2 | The **asmDB bearer token** placed in Key Vault (I create the vault and give you the exact command; **do not send it to me in plaintext**) | the only secret I cannot manufacture |
| 3 | Decision: **Amoy testnet (free)** or **Polygon mainnet** for $SMILE? | my recommendation: Amoy first |
| 4 | ~~Confirm the daily publication time~~ — **settled: 10:00 Europe/Paris**, all year round (see [§3.4](#34-publishing-at-1000-paris-all-year)) | ✅ |
| 5 | Approval to request a **`gpt-image-2` quota increase** (capacity is 2 today) | job reliability |
| 6 | Confirm the **$SMILE economy parameters** in [§8.3](#83-the-economy-genesis-rain--bloom-burn--claim-pool): Genesis Rain of **1,000,000**, Bloom Fee of **100** (≈ 27 years of daily slimes). Happy with those, or do you want a different runway? | it is the one number that cannot be changed after deployment |
| 7 | Confirm we ship the chain in three steps — **2a anchor-only (no token at all)** first, then **2b $SMILE**, then **3 adoption** | de-risks the economy from the provenance |

---

> *"A slime is a place, a feeling and a friend, squished together."*
> — SLIMEDEX, volume one
