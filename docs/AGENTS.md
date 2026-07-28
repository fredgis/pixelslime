# AGENTS.md — how work is split on PIXELSLIME

Read this before touching anything. Read [`docs/PLAN.md`](PLAN.md) for *what* we are building; this
document is about *how we build it without stepping on each other*.

---

## The one rule

**One workstream owns one directory. Nobody writes outside their own.**

That is what makes parallel work safe. If two agents never touch the same file, merge conflicts are not
unlikely — they are structurally impossible.

If you genuinely need something changed outside your scope, **say so in your final report**. Do not
reach across the line.

---

## Ownership map

| Workstream | Branch | Owns, exclusively |
|---|---|---|
| **W0** contracts | `feat/w0-contracts` | `contracts/`, `docs/`, root config, `.github/` |
| **W1** infra | `feat/w1-infra` | `infra/` |
| **W2** codec | `feat/w2-codec` | `backend/app/codec/`, `backend/tests/codec/` |
| **W3** asmDB | `feat/w3-asmdb` | `backend/app/asmdb/`, `backend/tests/asmdb/` |
| **W4** AI | `feat/w4-ai` | `backend/app/ai/`, `backend/tests/ai/` |
| **W5** design | `feat/w5-design` | `frontend/src/design/` |
| **W6** frontend | `feat/w6-frontend` | `frontend/src/` except `design/`, `frontend/public/` |
| **W7** backend | `feat/w7-backend` | `backend/app/api/`, `core/`, `storage/`, `backend/app/main.py` |
| **W8** job | `feat/w8-job` | `backend/app/jobs/` |
| **W9** chain | `feat/w9-chain` | `chain/`, `backend/app/chain/` |
| **W10** QA | `feat/w10-qa` | `tests/e2e/` |

`contracts/` is **read-only** to everyone except W0. It is the shared truth; if it is wrong, report it,
do not patch it locally.

---

## The contracts you must obey

| File | Binding on |
|---|---|
| `contracts/card.schema.json` | W2, W4, W7 — the card shape |
| `docs/CODEC.md` | W2 — **normative**; the implementation follows the document, not the reverse |
| `contracts/cards/*.json` | W2 — must encode and round-trip exactly |
| `contracts/openapi.yaml` | W6, W7 — the API surface, to the character |
| `contracts/design-tokens.json` | W5, W6 — colours, type, motion, rarity data |
| `assets/psdict_v1.bin` | W2 — the DEFLATE dictionary, pinned by `version = 0x01` |
| `docs/mockup/index.html` | W5, W6 — the visual reference of record |

---

## Definition of done

Nothing is finished until **all** of these hold.

- [ ] Unit tests pass, and they test behaviour rather than restating the implementation
- [ ] `ruff check` and `ruff format --check` clean (Python) · `tsc --noEmit` and `eslint` clean (TS)
- [ ] `mypy --strict` clean on new Python modules
- [ ] Public functions have docstrings explaining **why**, not what
- [ ] No secret, token, connection string or key in any file — ever
- [ ] Errors are raised loudly; nothing is silently truncated, defaulted or swallowed
- [ ] Documentation touching your area is updated

---

## Conventions

**Python 3.12.** `ruff` for lint and format, `mypy --strict`, `pytest`. Type-annotate everything.
Prefer `pathlib` over `os.path`, `httpx` over `requests`, dataclasses or Pydantic over loose dicts.

**TypeScript.** `strict: true`. No `any`. React function components with hooks. Tailwind for styling,
design tokens for values — never a hard-coded hex.

**Errors.** Define one exception type per module (`CodecError`, `AsmDbError`, `GenerationError`).
Never `except Exception: pass`. Never return `None` to mean failure.

**Logging.** `structlog`, JSON to stdout. Log the card serial on every pipeline step so a bad day can be
reconstructed. **Never log the asmDB bearer, a Key Vault secret or a private key.**

**Secrets.** Read from Key Vault via `DefaultAzureCredential` at startup, hold in memory, never write to
disk, never return in a response, never log. There is no `.env` with real values in this repository.

---

## Things that will bite you

1. **asmDB integers are JSON strings.** `{"id": "16", "value": "20260728"}`. A `u64` does not survive a
   JavaScript `number`. Never parse them into JS numbers.
2. **asmDB `content` is text, not binary.** Valid UTF-8, ≤ 175 bytes, **no NUL, CR or LF**. This is
   enforced server-side and it is why PSC-1 exists.
3. **asmDB sends no CORS headers.** The browser cannot call it, by design. Everything goes through the
   backend.
4. **The free asmDB tier sleeps.** Warm it with `GET /health` and retry on `instance_starting`.
5. **`gpt-image-2` rejects `image` on `/generations`.** Reference images go to `/images/edits`, as
   `image[]` (plural — the singular form refuses duplicates).
6. **Image size must be divisible by 16.** The card is `1024x1536`.
7. **Container Apps cron is UTC only.** Hence `0 8,9 * * *` plus a `Europe/Paris` hour guard.
8. **Rate limit is 2 requests / 60 s** on `gpt-image-2`. Irrelevant at one card a day, but do not fire
   bursts in tests — record cassettes instead.

---

## Working against a neighbour that does not exist yet

Nobody blocks on anybody:

- **W6** generates a mock server from `contracts/openapi.yaml` and builds the whole UI against it.
- **W7** codes against a fake asmDB (an in-memory dict honouring the same 175-byte rules).
- **W4** records real AI responses once as cassettes, then replays them offline forever.
- **W2** has `contracts/cards/*.json` and `docs/CODEC.md`, and needs nothing else at all.

---

## Reporting back

When you finish, report:

1. What you built, in one paragraph
2. The exact commands you ran to verify it, and their output
3. Anything you found that contradicts `docs/PLAN.md` — **this is the most valuable thing you can tell
   us**, so do not soften it
4. Anything you need from another workstream

If you discover the plan is wrong, say so plainly. The plan has already been corrected twice by exactly
that kind of pushback, and it was better both times.
