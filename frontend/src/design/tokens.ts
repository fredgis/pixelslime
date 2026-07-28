/**
 * PIXELSLIME design tokens — the single source of truth for every colour, font,
 * radius, shadow and motion value in the design system.
 *
 * WHY this file exists: `contracts/design-tokens.json` is owned by W0 and is the
 * canonical contract, but a JSON file gives us no types and cannot be imported as
 * literals into TSX without a runtime fetch. This module mirrors that JSON exactly
 * and re-exports it as `as const` typed values. It is the ONLY place in the design
 * system where a raw hex string may appear — every component references these
 * tokens (directly, or via the CSS custom properties emitted in globals.css).
 *
 * If a value here disagrees with contracts/design-tokens.json, the JSON wins and
 * this file is the bug. Keep them in lock-step.
 */

/** Core brand palette (light theme). */
export const color = {
  cream: '#FFF6E5',
  paper: '#FFFDF7',
  bubblegum: '#FF8FC5',
  mint: '#7FE3C0',
  sky: '#8FD3FF',
  grape: '#8B6FE8',
  sunbeam: '#FFD86B',
  coral: '#FF7A59',
  ink: '#2B1B4A',
  inkSoft: '#5B4A7D',
} as const;

/** MOONLIT PUNIVERSE — the dark theme overrides. */
export const night = {
  cream: '#1A1230',
  paper: '#241A3F',
  ink: '#FFF1D6',
  inkSoft: '#C3B0E8',
} as const;

/**
 * Rarity table. `house` is the in-world name shown to Keepers, `weight` is the
 * seeded roll probability, `yieldMultiplier` scales $SMILE, `adoptPrice` is the
 * SLIMEDEX Vault cost. Ordered from most common to rarest.
 */
export const rarity = {
  COMMON: { house: 'Puddle', color: '#9FB4C7', weight: 0.45, yieldMultiplier: 1, adoptPrice: 200 },
  UNCOMMON: { house: 'Dewdrop', color: '#7FE3C0', weight: 0.27, yieldMultiplier: 2, adoptPrice: 400 },
  RARE: { house: 'Prism', color: '#8FD3FF', weight: 0.17, yieldMultiplier: 4, adoptPrice: 900 },
  EPIC: { house: 'Aurora', color: '#C08BFF', weight: 0.08, yieldMultiplier: 8, adoptPrice: 2000 },
  LEGENDARY: { house: 'Starlight', color: '#FFD86B', weight: 0.025, yieldMultiplier: 20, adoptPrice: 6000 },
  MYTHIC: { house: 'Dreamdrop', color: '#FF8FC5', weight: 0.005, yieldMultiplier: 100, adoptPrice: 25000 },
} as const;

/** The 16 slime types — four bits, sixteen moods. */
export const typeColor = {
  FAIRY: '#FF8FC5',
  FOREST: '#6BC98A',
  WATER: '#5FB8E8',
  EMBER: '#FF7A59',
  STORM: '#8B6FE8',
  STONE: '#A08B7A',
  SUGAR: '#FFB3D9',
  GHOST: '#B0A8D8',
  METAL: '#93A4B5',
  COSMIC: '#6B5BD6',
  BLOOM: '#FF9EBB',
  FROST: '#9FE0F0',
  SLUDGE: '#8FA860',
  BEAM: '#FFD86B',
  PAPER: '#E8D9B8',
  DREAM: '#C08BFF',
} as const;

export const font = {
  pixel: "'Press Start 2P', monospace",
  round: "'M PLUS Rounded 1c', system-ui, sans-serif",
  stat: "'Silkscreen', monospace",
} as const;

export const radius = {
  sm: '12px',
  md: '16px',
  lg: '22px',
  xl: '26px',
  pill: '999px',
} as const;

export const border = { width: '4px', color: color.ink } as const;

export const shadow = {
  card: '0 10px 0 rgba(43,27,74,.14), 0 18px 40px rgba(43,27,74,.20)',
  /** Same card shadow, tuned for the dark theme. Not present in the JSON; see report. */
  cardNight: '0 10px 0 rgba(0,0,0,.45), 0 18px 40px rgba(0,0,0,.55)',
  chunk: '0 6px 0 #2B1B4A',
} as const;

export const motion = {
  /** The signature squash-and-stretch overshoot. */
  easing: 'cubic-bezier(.34,1.56,.64,1)',
  fast: '140ms',
  base: '240ms',
  slow: '600ms',
} as const;

export const cardDimensions = {
  width: 1024,
  height: 1536,
  aspectRatio: '1024/1536',
  thumbWidth: 512,
  thumbHeight: 768,
} as const;

/**
 * Bespoke art palette for the procedural <SlimeSprite/>. These pixel-art hues do
 * not map onto brand tokens (petal white, mouth pink, horn lavender…), so they
 * live here to keep tokens.ts the single home for every hex in the system.
 */
export const sprite = {
  eye: color.ink,
  eyeShine: '#FFFFFF',
  blush: color.bubblegum,
  mouthDark: color.ink,
  mouthPink: '#FF6FA5',
  accessory: {
    flowerPetal: '#FFF3F7',
    flowerCore: color.sunbeam,
    flowerLeaf: color.mint,
    leaf: typeColor.FOREST,
    leafDark: '#4FA96C',
    star: color.sunbeam,
    starShine: '#FFF0B8',
    hornLight: '#FFFFFF',
    hornDark: '#E7DCFF',
  },
} as const;

/** The six-colour confetti / title / background-slime rotation. */
export const confettiPalette = [
  color.bubblegum,
  color.sunbeam,
  color.mint,
  color.sky,
  color.grape,
  color.coral,
] as const;

export type Tokens = {
  color: typeof color;
  night: typeof night;
  rarity: typeof rarity;
  typeColor: typeof typeColor;
  font: typeof font;
  radius: typeof radius;
  border: typeof border;
  shadow: typeof shadow;
  motion: typeof motion;
  cardDimensions: typeof cardDimensions;
  sprite: typeof sprite;
};

export const tokens: Tokens = {
  color,
  night,
  rarity,
  typeColor,
  font,
  radius,
  border,
  shadow,
  motion,
  cardDimensions,
  sprite,
};

export default tokens;
