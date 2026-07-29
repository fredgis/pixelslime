<div align="center">

<img src="docs/assets/banner.png" alt="PIXELSLIME — PuniPuni Paradise" width="820">

### ✦ ぷにぷに ✦ &nbsp;**One slime per dawn.**

*A rainbow crashed above the clouds, and it rained pixels.*<br>
*Wherever a pixel landed on something happy, the thing went soft, wobbled twice,*<br>
*and opened two shiny eyes.*

<br>

[![Status](https://img.shields.io/badge/status-BUILT-7FE3C0?style=for-the-badge)](docs/RUNBOOK.md)
[![Plan](https://img.shields.io/badge/read-the%20plan-FF8FC5?style=for-the-badge)](docs/PLAN.md)
[![Runbook](https://img.shields.io/badge/deploy-the%20runbook-8B6FE8?style=for-the-badge)](docs/RUNBOOK.md)
[![Tests](https://img.shields.io/badge/tests-694%20backend%20%C2%B7%20113%20chain-FFD86B?style=for-the-badge)](#-verified-not-asserted)

</div>

---

**PIXELSLIME** generates **one unique AI collectible card every day at 10:00 Europe/Paris**, catalogues it
in a public gallery, packs it into **175 bytes** inside an [asmDB Cloud](https://www.asmdb.cloud)
database, and anchors it on-chain with the **$SMILE** token.

> [!TIP]
> **So you want to keep a slime.**
>
> Slimes don't eat — they absorb **moods**. One that naps in a sunbeam turns warm and golden. One raised
> in a library grows clever and quiet. One that meets a cat learns to purr. That's why no two are ever
> the same: a slime is a place, a feeling and a friend, squished together.
>
> Every dawn, exactly **one** condenses out of the Pixel Rain — and a **Slime Keeper** has until the next
> dawn to catalogue it before it drifts away. Rare ones arrive wrapped in colours that shouldn't exist.
> The rarest, the **Dreamdrop**, shows up about eighteen times a decade; they say those are dreams that
> got lost on the way to someone.
>
> That's the whole job. You're a Keeper now. 🫧

<br>

## 🌸 Today's Bloom

The card of the day arrives face down. Click it, and it flips.

<div align="center">
  <img src="docs/assets/home.png" alt="Today's Bloom — the daily card reveal" width="920">
</div>

<br>

## ◈ Slime Profile

Every card exposes its own **provenance**: the exact packed bytes as they live in the database.

<div align="center">
  <img src="docs/assets/profile.png" alt="Slime Profile — stats, lore and the 175 packed bytes" width="760">
</div>

<br>

## 🫧 What makes this interesting

| | |
|---|---|
| **175 bytes** | An asmDB row gives you `175` bytes of UTF-8 for content — no NUL, no CR, no LF. A whole trading card has to fit in that. It becomes the **PSC-1 codec**: a 32-byte header plus dictionary-DEFLATE text, Z85-encoded, chunked across rows. |
| **The constraint is the feature** | Those same packed bytes are what gets hashed with keccak256 on-chain. The chain proves a slime existed exactly like that, on that day — **without duplicating a single byte of it**. |
| **No keys anywhere** | API key auth is disabled on the model endpoint, so the backend authenticates with a **managed identity**. The database bearer lives in Key Vault. Nothing reaches the browser. |
| **No login, no personal data** | The site is fully public. Which slimes you've discovered lives in your own `localStorage` — nothing about a visitor is ever sent to the server. |
| **It runs itself** | A cron job wakes at 10:00 Paris, rolls a rarity, writes the card, paints it, verifies it, stores it, and goes back to sleep. |

<br>

## 📚 Start here

| Document | What it is |
|---|---|
| **[`docs/PLAN.md`](docs/PLAN.md)** | The complete plan — verified API facts, Azure architecture, the 175-byte codec, the AI pipeline, the $SMILE economy, and an 11-workstream split designed for parallel agents |
| **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)** | **Deploying and operating it** — the remaining rollout steps, plus backfill, token rotation and troubleshooting |
| **[`docs/CODEC.md`](docs/CODEC.md)** | The normative PSC-1 specification |
| **[`docs/AGENTS.md`](docs/AGENTS.md)** | Workstream ownership, definition of done, and the gotchas that will bite you |
| **[`docs/mockup/index.html`](docs/mockup/index.html)** | The original clickable mockup. Open it in a browser |

<br>

## 🗂 What's in the repo

```
docs/            PLAN.md, RUNBOOK.md, CODEC.md, AGENTS.md, the mockup
contracts/       card schema, openapi.yaml, PSC-1 fixtures, design tokens, lookups
infra/           Bicep — identity, Key Vault, Storage, ACR, Container Apps, RBAC
backend/app/     codec · asmdb · ai · api · core · storage · jobs · chain
frontend/src/    design system + the five screens
chain/           Foundry — SmileToken, PixelSlimeCard, ClaimPool, SlimeAdoption
tests/e2e/       real frontend against real backend
scripts/         template cleanup, dictionary build, contract validation
Dockerfile       one image, two entrypoints: the API and the daily job
```

<br>

## 🔬 Verified, not asserted

| | |
|---|---|
| Backend | **694 tests**, `mypy --strict` clean across 66 modules |
| Chain | **46 Solidity + 67 Python** tests; 3,650 blooms drain the Genesis Rain to exactly zero |
| Frontend | **0 axe violations** on all five screens, ~80 KB gzipped initial load |
| Integration | Real frontend against real backend; every response validated against the contract |
| Codec | A whole Mochibo card fits in **65 of the 175 available bytes**, in a single row |

```bash
python scripts/validate_contracts.py   # contracts are internally consistent
python scripts/verify_rows.py          # every emitted row is legal for asmDB
cd backend && pytest tests             # 694 passed
cd chain   && forge test               # 46 passed
```

<details>
<summary><b>Why the template needed cleaning</b></summary>

<br>

`mochibo-original.png` looks like it has a transparent background. It does not — it is `RGB` with **no
alpha channel at all**, and the "transparency" is an 8-pixel checkerboard painted into the pixels.

Handing that to an image model as a style reference is asking it to **paint a checkerboard**. So the
pattern is flood-filled from the borders and converted into a real alpha channel:

```bash
python scripts/clean_template.py \
  assets/template/mochibo-original.png \
  assets/template/mochibo.png
```

```
transparent : 279,475 / 1,572,864 px  (17.8%)
corner alpha: [0, 0, 0, 0]   centre alpha: 255
```

Requires `pillow`, `numpy` and `scipy`.

</details>

<br>

## 🎴 Rarity tiers

| | Tier | House name | Odds |
|---|---|---|---:|
| ⬜ | `COMMON` | **Puddle** | 45 % |
| 🟩 | `UNCOMMON` | **Dewdrop** | 27 % |
| 🟦 | `RARE` | **Prism** | 17 % |
| 🟪 | `EPIC` | **Aurora** | 8 % |
| 🟨 | `LEGENDARY` | **Starlight** | 2.5 % |
| 🟥 | `MYTHIC` | **Dreamdrop** | 0.5 % |

Rolled in code with a seeded weighted random — never left to the model — with a pity timer that forces
a `RARE` or better if fourteen days pass without one.

<br>

---

<div align="center">

*"A slime is a place, a feeling and a friend, squished together."*<br>
<sub>— SLIMEDEX, volume one</sub>

<br>

**✦ COLLECT THEM ALL ✦**

</div>
