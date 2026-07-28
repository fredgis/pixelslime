# 🫧 pixelslime

A Pixel Slime application based on the asmDB Cloud database.

**One unique AI-generated PixelSlime card, every day at 10:00 Europe/Paris**, catalogued in a public
gallery and (later) anchored on-chain with the **$SMILE** token.

> **Status: PLANNING — no application code yet, no Azure resources created yet.**

## Start here

| Document | What it is |
|---|---|
| **[`docs/PLAN.md`](docs/PLAN.md)** | The complete plan: verified API facts, architecture, the 175-byte codec, the AI pipeline, the $SMILE economy, and the multi-agent workstream split |
| **[`docs/mockup/index.html`](docs/mockup/index.html)** | Clickable static mockup of the site — open it in a browser |

## What's in the repo right now

```
docs/PLAN.md                          the plan (read this first)
docs/mockup/index.html                the visual mockup
assets/template/mochibo.png           the style reference card, RGBA with real alpha
assets/template/mochibo-original.png  the original, RGB with a painted-on checkerboard
scripts/clean_template.py             turns the checkerboard into a real alpha channel
```

## Reproduce the template cleanup

```bash
python scripts/clean_template.py assets/template/mochibo-original.png assets/template/mochibo.png
```

Requires `pillow`, `numpy` and `scipy`.
