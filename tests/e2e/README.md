# W10 — QA & end-to-end integration report

**The question this workstream exists to answer:** W6 built the frontend against an MSW
mock generated from `contracts/openapi.yaml`; W7 built the backend against fakes. Both
pass their own tests. *Nobody had ever run the real frontend against the real backend.*
This harness does exactly that and reports whether the contract-first approach actually
held.

**Verdict:** The two sides **genuinely agree on the wire shapes** — every real `/api/*`
response validated against the contract schema, and all five screens render and behave
correctly against the real backend (38/38 Playwright checks pass, 0 axe violations per
screen). **But the contract did *not* fully bind.** Several `Always present` guarantees
in the contract are prose-only — they are not encoded in the schema's `required` arrays —
and W7 quietly dropped one of them (`onChain`) while W6 faithfully emits it. Because the
schema is looser than the prose, the drift passes validation. There are **3 located W7
defects** and **5 contract-vs-implementation divergences**, detailed below. None was
patched (W10 reports, it does not fix).

---

## How to run it

Everything lives under `tests/e2e/` (W10's exclusive scope). From that directory:

```powershell
npm install          # once
npm run harness      # build (mock off) → boot real backends → Playwright → teardown
```

Verified toolchain: Node 24, Python 3.12, `uvicorn` 0.51 / `fastapi` 0.140, Playwright
1.61.1, `@axe-core/playwright` 4.12.1. Useful toggles: `SKIP_BUILD=1`, `NO_TODAY=1`,
`PW_ARGS="contract.spec.ts"`.

The harness (`harness.mjs`):
1. Builds the SPA with **`VITE_USE_MOCK=false`** so it talks to a real same-origin `/api`
   (verified: no MSW/mock chunk in `frontend/dist/assets`).
2. Boots the **primary** backend — `uvicorn app.main:app`, `FAKE_BACKEND=1`, in-memory
   asmDB+blob fakes seeded from `contracts/cards/*.json`, serving `frontend/dist`.
3. Boots a **supplementary** backend — `serve_today.py`: the *same real app* plus one
   synthetic card dated today, so the reveal ceremony and `/api/cards/today` can be
   exercised (the pure seed can't — see Limitations). It uses only the backend's public
   `create_app(source=…, blob=…)` injection seam; no W6/W7 code is modified.
4. Waits for both `/api/health` → 200, runs Playwright, tears both servers down in a
   `finally` (PID-based kill), even on failure.

Artifacts land in `tests/e2e/reports/` (contract table, axe, perf, pagination/sort,
dayNumber, Playwright HTML) and screenshots in `tests/e2e/screenshots/`.

---

## Do the frontend and backend agree? (contract conformance)

**Yes, at the schema level.** Every contract operation was hit against the real backend
and its JSON validated against `contracts/openapi.yaml` (see
`reports/contract-table.md`). Full table — all schema-checked responses are **valid**:

| Method | Path | Real status | Schema |
| --- | --- | --- | --- |
| GET | `/api/health` | 200 | ✅ valid |
| GET | `/api/cards/today` | 404 (no bloom on run date) | ✅ valid (Error) |
| GET | `/api/cards` (+ filters/sort) | 200 | ✅ valid |
| GET | `/api/cards/{serial}` (1, 900, 65535) | 200 | ✅ valid |
| GET | `/api/cards/{serial}` (absent, in range) | 404 | ✅ valid (Error) |
| GET | `/api/cards/{serial}` (out-of-range / non-int) | **422** | ⚠️ undocumented (see D4) |
| GET | `/api/cards/{serial}/raw` (1, 900, 65535) | 200 | ✅ valid |
| GET | `/api/cards/{serial}/image` | 200 `image/png`, `immutable`, **304** on revalidate | n/a (binary) |
| GET | `/api/cards/{serial}/thumb` | 200 `image/webp`, `immutable`, **304** on revalidate | n/a (binary) |
| GET | `/api/stats` | 200 | ✅ valid |
| GET | `/api/nft/{serial}` (1, 900, 65535) | 200 | ✅ valid (ERC-721) |
| POST | `/api/admin/generate` (no token) | 401 | n/a (guarded, off by default) |
| GET | `/api/does-not-exist` | 404 `application/json` | n/a (not swallowed by SPA) |

Media routes serve **real bytes through the proxy** with `Cache-Control: public,
max-age=31536000, immutable` and a working conditional-GET **304**. The SPA fallback
serves deep routes on hard refresh (`/slime/1` → 200 HTML) while `/api/*` unknown paths
stay JSON 404 — the router boundary holds.

> **The important nuance:** every response is *schema-valid*, yet real behaviour still
> diverges from the contract's **prose** in several places (below). That is only possible
> because the schema's `required`/typing is looser than the prose. So "all green" on
> validation is not the same as "the contract bound both sides." It did not, quite.

---

## Screenshots — real backend vs W6's mock

Five screens captured against the real backend in `tests/e2e/screenshots/`, alongside the
mock-driven baseline in `frontend/screenshots/`. **Structure and behaviour match; the data
differs** because the real backend is seeded from only 3 `contracts/cards` (serials 1
"Mochibo", 900 "Thundernub", 65535 "Zzyxqvwuunthorp"), whereas the mock ships 14 cards.

| Screen | Real (W10) | Mock (W6) | Difference & cause |
| --- | --- | --- | --- |
| Home `01-today` | Graceful *"Today's bloom hasn't arrived."* error state | Face-down card + countdown | **Expected, not a bug.** No seed card blooms on the run date (Mochibo's mint date is *yesterday*), so `/api/cards/today` 404s and the page degrades correctly. The reveal ceremony is proven separately ↓ |
| Reveal `02-today-revealed` | Real card "Todaybloom" flips in; stat bars (28/55/65/95) **exactly match `/api/cards/today`** | Rich card art | Ceremony works E2E. Card art is a flat rectangle because the **fake blob store serves 100-byte placeholder PNG/WebP**, not real art. Ribbon reads **"DAY 4"** for serial 2 — the dayNumber defect made visible (D-defect 3) |
| Dex `03-dex` | 3 real cards, all locked "UNDISCOVERED" (fresh context) | 14 cards, 3 discovered | Identical locked-tile rendering. Difference = seed size + which serials have localStorage discovery |
| Dex filter `04-dex-legendary` | LEGENDARY → exactly 1 tile (PS-0900), header "1 HAVE BLOOMED" | Filtered set | Rarity filter works against the real API |
| Profile `05/06` | Thundernub (900); **"ANCHOR PENDING"** badge; provenance panel shows genuine rows (`183 bytes · 2 rows`, `cardHash 0x…`, tags `psc.900.0/1`, row-1 `VAL:-14401`) | Full card + provenance | Renders real data. "ANCHOR PENDING" is the visible symptom of defects 1+2. Card art is a placeholder rectangle (fake blob) |
| `07-lab` / `08-bank` / `10-design` | Render fully | Same | Static, backend-independent — visually identical to the mock |
| `09-notfound` | `/slime/4242` → clean *"No slime with that serial."*, chrome intact | (n/a) | A missing serial is a graceful in-UI 404, not a crash |

Reduced-motion variants (`rm-*`) render correctly against the real backend.

---

## Accessibility (axe-core, real backend)

`@axe-core/playwright` with WCAG 2.0/2.1 A+AA on every screen — **0 violations each**,
matching W6's mock-driven baseline exactly (`reports/axe-report.json`):

| Screen | `/` | `/dex` | profile | `/lab` | `/bank` |
| --- | --- | --- | --- | --- | --- |
| Violations | 0 | 0 | 0 | 0 | 0 |

## Performance budget (real backend)

`reports/perf.json`. Comfortable, and — asserted — **no mock chunk shipped to production**:

| Route | JS chunks | JS transferred | JS decoded | LCP |
| --- | --- | --- | --- | --- |
| `/` (first load) | 15 | ~237 KB | ~232 KB | ~0.50 s |
| `/slime/1` (image-heavy) | 12 | ~233 KB | ~230 KB | ~0.58 s |

(`frontend/dist/assets`: 22 JS files, 265 KB total.)

---

## Defects (located; **not fixed** — reporting is the deliverable)

### D1 — `Card` (detail) omits `onChain`, which the contract says is *"Always present"*  → **W7**
- **Where:** `backend/app/core/serialize.py`, `card_detail()` — the returned `payload`
  dict never sets `onChain`. (Grep confirms `onChain` appears **only** at
  `serialize.py:60`, inside `card_summary`.)
- **Contract:** `Card.onChain` — *"Convenience mirror of `chain != null` … **Always
  present.**"* (`contracts/openapi.yaml`).
- **Evidence:** `GET /api/cards/65535` keys are `… mood, name, palette, personality …` —
  **no `onChain`**. Meanwhile `CardSummary.onChain` *is* emitted
  (`serialize.py:card_summary` → `card.flags.on_chain`).
- **Why it passes validation anyway:** `onChain` is **not** in the `Card.required` array,
  so a loose schema check (and the generated `frontend/src/api/schema.ts`, which types it
  `onChain?: boolean`) both accept its absence. The guarantee is prose-only.

### D2 — `Card.chain` is hard-coded `null` for every card, even on-chain ones  → **W7**
- **Where:** `backend/app/core/serialize.py:95`, `card_detail()` sets `"chain": None`
  unconditionally.
- **Evidence + user-visible contradiction:** seed serial **65535 has `flags.on_chain =
  true`**, so the gallery summary returns `onChain: true`, **but** its detail returns
  `chain: null` and omits `onChain`, so `ProfilePage` (`data.onChain && data.chain`)
  renders **"ANCHOR PENDING"**. The same card is *on-chain in the grid* and *not anchored
  on its own profile*. With `chain` always `null`, the profile's "ON-CHAIN #tokenId" badge
  is unreachable against this backend. (W7's own code comment acknowledges chain is null
  "until PSC-1 part 8 is decodable," but nothing reconciles that with the `on_chain` flag
  or the `onChain` mirror the contract promises.)

### D3 — `/api/cards/today` top-level `dayNumber` ≠ `card.dayNumber`  → **W7**
- **Where:** `backend/app/api/routes_cards.py`, `get_today()` returns `"dayNumber":
  index.size`; `serialize.py:card_detail` sets `card.dayNumber = card.serial`.
- **Contract:** top-level `dayNumber` — *"**Always equal to `card.dayNumber`.**"*
- **Evidence (live):** against the supplementary backend, `reports/today-daynumber.json`
  shows `topLevelDayNumber: 4` (= number of cards in the index) vs `cardDayNumber: 2` (=
  serial). The UI ribbon renders **"DAY 4"** for a serial-2 card (`02-today-revealed.png`).
  The two coincide only when today's card is the highest serial in a contiguous index — a
  latent bug the "newest-is-today" production case masks. Two different formulas for one
  value the contract says must be identical.

---

## Contract-vs-implementation divergences ("is the contract actually binding?")

These are cases where the *file* says one thing and the running code says another. The
most important category is where **both sides are individually schema-valid but semantically
incompatible**, because that is exactly the drift a contract is supposed to prevent.

### V1 — `onChain` "Always present" is unenforced; the two sides drift  *(contract not binding)*
The prose mandates `onChain` on `Card`; the schema does **not** (`required` omits it), so
`openapi-typescript` generated `onChain?: boolean`. **W6 honours the prose** —
`frontend/src/mocks/data.ts` emits `onChain: chain != null` on every detail card. **W7
drops it** (D1). The schema was too loose to catch the disagreement. *This is the single
clearest sign the contract did not fully bind.*

### V2 — `chain` is populated by the mock but never by the backend
`frontend/src/mocks/data.ts` builds real `chain` objects (`tokenId`, `txHash`,
`blockNumber`, `explorerUrl`) for anchored serials; **W7 always returns `chain: null`**
(D2). Both keep `chain` present-as-a-key (contract-compliant on that narrow point), but
they disagree on whether *any* card is ever anchored — so the whole on-chain UI path is
live in the mock and dead against the backend.

### V3 — provenance row `value`: **negative continuation vs repeated date** *(both valid, incompatible)*
Contract: rows have `value: { type: string, example: "20260728" }`, "integers are strings"
— it never defines continuation-row semantics. **W7** emits the mint date for row 0 and
**`-rowid` for continuation rows** (observed `VAL:-14401` for `psc.900.1`, see
`06-profile-provenance.png`). **W6** (`data.ts:buildRaw`) emits **the same date string for
every row**. Both pass `type: string`; a client that parsed `value` as a date would break
on the real backend. Underspecified contract → two valid but non-interchangeable
implementations.

### V4 — invalid serial: real backend **422**, mock **404**, contract documents neither-as-422
Contract documents only `200`/`404` for `/api/cards/{serial}` (Serial param
`minimum:1, maximum:65535`). **W7** relies on FastAPI param validation → **422** for
`/api/cards/99999` and `/api/cards/abc` (verified). **W6** (`handlers.ts` `parseSerial`)
clamps invalid serials to **404** — matching the contract. So the mock is contract-faithful
and the backend emits an undocumented status. (User-visibly both still land on the graceful
error state, so this is low-severity, but it is real drift.)

### V5 — `streamBytes` / the "175 bytes" invariant
The product copy and mock frame every card to exactly **175 bytes** (`data.ts:frameRecord`,
`RECORD_BYTES = 175`). The **real** PSC-1 stream is variable — **183 bytes** for Thundernub
(`06-profile-provenance.png`). The contract only says `streamBytes` is "length of the PSC-1
stream," so neither violates the schema, but the celebrated "175 bytes of pure joy"
invariant is a mock-only artifact.

### Meta — the contract file is internally inconsistent
`contracts/openapi.yaml` declares `openapi: 3.1.0` (JSON Schema 2020-12) but uses the
**3.0-only `nullable: true`** keyword (on `biome`, `mood`, `companion`, `chain`), which is
not valid in 3.1 and is silently ignored by strict 2020-12 tooling. The validator here
normalises it (`nullable:true` → `type:[…, "null"]`) to avoid false positives — but the
fact that this normalisation is *necessary* means the contract file itself would mislead a
conformant 3.1 validator.

---

## Limitations (honest scope notes)

- **3-card seed.** The real backend seeds only `contracts/cards/*.json` (serials 1, 900,
  65535). Consequences, each handled explicitly:
  - **Pagination page-1-vs-page-2 in the *UI*** can't be shown: `DexPage` only renders
    pager controls when `total > 24`. Verified instead at the **API level** with
    `size=1`: pages returned `[65535] → [900] → [1] → []`, no repeat, no skip, `hasMore`
    flips correctly (`reports/pagination-and-sort.json`).
  - **Sort tie-break by `serial` descending** is **unobservable** — no two seed cards share
    a sort key, so a tie never arises. Sorts are otherwise deterministic and correct
    (`newest`, `oldest`, `rarest` verified). This one contractual guarantee could not be
    exercised against real data; flagged rather than claimed.
  - **`/api/cards/today` = 404** on the run date, so the flagship reveal was proven via the
    supplementary `serve_today.py` backend, which is the real app + one card dated today.
- **Fake blob art.** Image/thumb routes serve real *bytes* with correct headers and 304s,
  but the fake blob store returns tiny placeholder images, so card artwork renders as flat
  colour rectangles. This is a property of the offline fake, not a frontend/contract fault.

## What I did not touch

No changes to `backend/` or `frontend/`. No `git commit` / `git push`. All new code is
under `tests/e2e/`.
