# PIXELSLIME Design System (W5)

`frontend/src/design/` — the reusable React + TypeScript + Tailwind design system,
ported faithfully from the approved `docs/mockup/index.html`. Tokens, a Tailwind
preset, the global stylesheet, ~13 components and a self-contained preview page.

Everything is driven by `tokens.ts` (the single source of every hex, mirrored from
`contracts/design-tokens.json`). No component hard-codes a colour.

---

## ⚠️ REQUIRED FIRST STEP — mount Tailwind in your app

`globals.css` deliberately ships **no** `@tailwind` directives. The app owns
Tailwind's entry point; emitting the directives here too would double-generate
Tailwind's base/preflight when both stylesheets are imported. So **your app's CSS
entry must contain the three directives itself**:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

If you skip this, **zero Tailwind utilities are generated** and every page collapses
to a broken single column — yet the design system's own `.ps-*` classes keep working,
so it looks like a layout bug rather than a missing build step. Import order at the
app root: your Tailwind entry **first**, then `import '@/design/globals.css';`, so the
`.ps-*` identity wins over Tailwind's preflight. (See `preview.entry.tsx` +
`preview-tailwind.css` in this folder for exactly this wiring.)

---

## What W6 must merge

The `package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.ts`,
`postcss.config.js`, `index.html`, `preview.entry.tsx`, `preview-tailwind.css`,
`screenshot.mjs` and `*.png` in this folder are a **dev-only harness** so W5 can
typecheck and preview in isolation. W6 owns the real app config and should **not**
run `npm install` in here. Instead:

### 1. `frontend/package.json`
Merge these into the app's dependencies / devDependencies:

```jsonc
"dependencies": {
  "react": "^18.3.1",
  "react-dom": "^18.3.1"
},
"devDependencies": {
  "@types/react": "^18.3.12",
  "@types/react-dom": "^18.3.1",
  "@vitejs/plugin-react": "^4.3.4",
  "autoprefixer": "^10.4.20",
  "postcss": "^8.4.49",
  "tailwindcss": "^3.4.17",
  "typescript": "^5.6.3",
  "vite": "^5.4.11"
}
```

(The design system ships **no runtime dependencies of its own** beyond React.
`playwright` is only needed if W6 wants to re-run `screenshot.mjs`.)

### 2. `frontend/tsconfig.json`
The design system assumes a modern strict TS config. Ensure these are set (the
values used to get a clean `tsc --noEmit` here):

```jsonc
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  }
}
```

- `isolatedModules` is on, so the design system uses `import type { … }` everywhere.
  Keep it on (or at least don't fail the build without it).
- A `vite-env.d.ts` with `/// <reference types="vite/client" />` (and the `*.png`
  module shims here) must be part of the app's include so image imports typecheck.

### 3. `frontend/tailwind.config.ts`
Register the preset and make sure the content globs cover the design folder:

```ts
import type { Config } from 'tailwindcss';
import { pixelslimePreset } from './src/design/tailwind.preset';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  presets: [pixelslimePreset],
} satisfies Config;
```

You then get `bg-bubblegum`, `text-ink`, `bg-rarity-epic`, `text-type-fairy`,
`shadow-chunk`, `rounded-pill`, `ease-pop`, `animate-squish`, `animate-bobin`, etc.

### 4. Global stylesheet — import **once** at the app root
```ts
import '@/design/globals.css';
```
This provides the fonts, the light + `MOONLIT PUNIVERSE` theme variables, the dotted
paper surface (`.ps-surface`), the focus ring and every keyframe/`.ps-*` class the
components rely on. **The components will not look right without it.** Note this file
does **not** include the `@tailwind` directives — you mount those yourself (see the
⚠️ REQUIRED FIRST STEP at the top).

### 5. Dark theme
Toggle by setting `data-theme="night"` on `<html>` (or any wrapper):
```ts
document.documentElement.dataset.theme = isNight ? 'night' : '';
```

> ⚠️ **Theme-aware colours:** the Tailwind semantic tokens `cream`, `paper`, `ink`,
> `ink-soft` resolve to CSS custom properties, so `text-ink` / `bg-cream` **flip
> automatically** under `data-theme="night"` — but only because `globals.css` is
> imported. They do **not** support Tailwind opacity modifiers (`text-ink/50`); use a
> brand hue if you need alpha. Brand accents (`bubblegum`, `mint`, …), `rarity.*` and
> `type.*` are fixed identity colours and never flip.

---

## Consuming the components

```ts
import { SlimeCard, CardFlip, AnimatedTitle, StatBar, Confetti, tokens } from '@/design';
```

Map the API `CardSummary` onto the presentational `SlimeCardData`:

```ts
const card: SlimeCardData = {
  serial: c.serial,
  name: c.name,
  rarity: c.rarity,
  type: c.type,
  level: c.level,
  imageSrc: c.thumbUrl,      // falls back to the procedural <SlimeSprite/> when absent
  // spriteColor / accessory / face are optional sprite-fallback hints
};
```

See `preview.tsx` for every component rendered in every meaningful state. W6 can wire
a `/design` route straight to `export function Preview()`.

### Component inventory
| Component | Purpose |
|---|---|
| `<AnimatedTitle>` | Hero wordmark: per-letter squash bounce, ぷにぷに eyebrow, typewriter subtitle, `rainbow` MYTHIC variant |
| `<SlimeSprite>` | Procedural 16×12 `crispEdges` pixel slime; deterministic from `baseColor`/`accessory`/`face` |
| `<SlimeCard>` | Slimedex tile; hover lift + pointer tilt, rarity-scaled holo sheen, `locked` silhouette, `isNew` flag |
| `<CardFlip>` | 3D flip reveal (controlled/uncontrolled); reduced-motion → crossfade; keyboard-operable button |
| `<StatBar>` | Segmented stat bar per stat (strength/endurance/agility/happiness) with colour+icon, staggered fill |
| `<RarityBadge>` `<TypePill>` `<Chip>` | Kawaii pills; auto AA-legible text via `readableText()` |
| `<PixelButton>` | Chunky `0 6px 0` press-down button; variants sunbeam/pink/mint/coral/ghost |
| `<Ribbon>` `<Countdown>` | Tilted banner; daily/one-shot countdown (cleans up its interval) |
| `<Confetti>` | Canvas burst; mount once near root, fire via ref; rAF loop torn down on unmount |
| `<HoloCard>` | Pointer/gyroscope holographic tilt for the profile view |

Hooks (also exported): `useReducedMotion`, `useTypewriter`, `usePointerTilt`,
`useConfetti`.

---

## Non-negotiables — how they're met
- **Reduced motion:** handled centrally, not per component. CSS `@media
  (prefers-reduced-motion: reduce)` in `globals.css` neutralises all animation and
  maps entrances to a fade; the JS `useReducedMotion()` hook gates the typewriter,
  confetti, tilt and the flip (→ crossfade).
- **Accessibility:** real `<button>`s (CardFlip/SlimeCard/PixelButton are keyboard
  operable), a visible on-brand dashed focus ring, `aria-label` on icon-only controls,
  `role="progressbar"` on stat bars, AA-legible pill text chosen by WCAG contrast, and
  full titles exposed via a visually-hidden `.ps-sr-only` span (never `aria-label` on a
  role-less element — informational pills carry `role="img"`/`role="timer"` so their
  label is announced as one unit). `npm run axe` reports **0 violations** on the preview
  (the only `incomplete` item is `color-contrast`, which axe cannot auto-compute over the
  dotted/gradient backgrounds; it was verified AA by hand).
  > **Accessibility contract for the app:** the components are axe-clean, but page-level
  > landmark rules (`landmark-one-main`, `region`) are the app's job — wrap your routes
  > in `<header>`/`<main>`/`<footer>` (the preview does this). SlimeCard's `locked` state
  > deliberately hides the name, type, rarity house tag **and** the holo intensity so a
  > silhouette never spoils its tier; a broken `imageSrc` degrades to the procedural
  > sprite via `onError`.
- **No `any`; `tsc --noEmit` clean** under `strict: true`.
- **Motion budget:** every discrete transition/reveal is ≤600 ms (flip and pop-in are
  capped at .6s). The ambient idle loops (squish/bob/breathe/pulse) are the mockup's
  "squash-and-stretch everywhere" charm and run continuously — see note below.

---

## Notes / decisions W6 & W0 should know
- **600 ms interpretation:** applied to discrete UI transitions and reveals. Infinite
  ambient idle animations (slime squish, title letter-hop, eyebrow pulse) are kept, as
  in the approved mockup. Flag if the owner wants those capped too.
- **AA vs the mockup's white text:** pills pick the higher-contrast of ink/paper via
  `readableText()`, so bright pills (SUGAR, BEAM, PAPER, MYTHIC) get dark text instead
  of the mockup's fixed white. This is a deliberate, small aesthetic deviation for AA.
- **`contracts/design-tokens.json` gaps** found during real component work:
  - No dark-theme card shadow — added `shadow.cardNight` in `tokens.ts`.
  - No procedural-sprite art palette (petal white, mouth pink, horn lavender, …) —
    added `tokens.sprite`. If sprites become a shared contract, promote this to JSON.
  - Stat-bar light/shade variants are derived at runtime from the base hue via
    `shade()`; no explicit tokens needed, but noted for parity.

## Dev commands (inside this folder only)
```
npm install        # dev harness deps (W6 does NOT need this)
npm run typecheck  # tsc --noEmit  → clean
npm run dev        # vite preview at http://localhost:5173/
npm run shot       # Playwright screenshots (needs `npx playwright install chromium`)
npm run axe        # @axe-core/playwright audit of the preview → 0 violations
```
