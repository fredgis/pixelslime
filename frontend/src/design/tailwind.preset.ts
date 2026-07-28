/**
 * PIXELSLIME Tailwind preset.
 *
 * WHY: W6 owns the app-level Tailwind config, but the palette, radii, shadows,
 * easing, fonts and signature keyframes must come from ONE place (these tokens),
 * not be re-typed per workstream. Register this preset and W6 immediately gets
 * `bg-bubblegum`, `text-type-fairy`, `bg-rarity-epic`, `shadow-chunk`,
 * `rounded-lg`, `ease-pop`, `animate-squish`, etc.
 *
 * Usage in W6's tailwind.config.ts:
 *   import { pixelslimePreset } from './src/design/tailwind.preset';
 *   export default { content: [...], presets: [pixelslimePreset] };
 */

import type { Config } from 'tailwindcss';
import { color, night, rarity, typeColor, font, radius, shadow, motion } from './tokens';

const rarityColors = Object.fromEntries(
  Object.entries(rarity).map(([key, value]) => [key.toLowerCase(), value.color]),
) as Record<string, string>;

const typeColors = Object.fromEntries(
  Object.entries(typeColor).map(([key, value]) => [key.toLowerCase(), value]),
) as Record<string, string>;

export const pixelslimePreset = {
  theme: {
    extend: {
      colors: {
        // Semantic surface/text tokens are theme-aware: they resolve to the CSS
        // custom properties from globals.css, so `bg-cream`, `text-ink`,
        // `text-ink-soft` automatically flip under [data-theme="night"]. This is
        // why globals.css MUST be imported at the app root. (Opacity modifiers
        // like `text-ink/50` are not supported on these four — use a brand hue.)
        cream: 'var(--ps-cream)',
        paper: 'var(--ps-paper)',
        ink: 'var(--ps-ink)',
        'ink-soft': 'var(--ps-ink-soft)',
        // Brand accents, rarity and type hues are fixed identity colours: they do
        // NOT flip with the theme, and support Tailwind opacity modifiers.
        bubblegum: color.bubblegum,
        mint: color.mint,
        sky: color.sky,
        grape: color.grape,
        sunbeam: color.sunbeam,
        coral: color.coral,
        night: {
          cream: night.cream,
          paper: night.paper,
          ink: night.ink,
          'ink-soft': night.inkSoft,
        },
        rarity: rarityColors,
        type: typeColors,
      },
      fontFamily: {
        pixel: [font.pixel],
        round: [font.round],
        stat: [font.stat],
      },
      borderRadius: {
        sm: radius.sm,
        md: radius.md,
        lg: radius.lg,
        xl: radius.xl,
        pill: radius.pill,
      },
      boxShadow: {
        card: shadow.card,
        'card-night': shadow.cardNight,
        chunk: shadow.chunk,
      },
      transitionTimingFunction: {
        pop: motion.easing,
      },
      transitionDuration: {
        fast: motion.fast,
        base: motion.base,
        slow: motion.slow,
      },
      keyframes: {
        squish: {
          '0%,100%': { transform: 'scale(1,1)' },
          '45%': { transform: 'scale(1.14,.86)' },
          '70%': { transform: 'scale(.94,1.08)' },
        },
        letterhop: {
          '0%,62%,100%': { transform: 'translateY(0) scale(1,1)' },
          '70%': { transform: 'translateY(-16px) scale(.9,1.14)' },
          '82%': { transform: 'translateY(0) scale(1.14,.88)' },
          '90%': { transform: 'translateY(0) scale(1,1)' },
        },
        hue: { to: { filter: 'hue-rotate(360deg)' } },
        bob: {
          '0%,100%': { transform: 'translateY(0) rotate(-2deg)' },
          '50%': { transform: 'translateY(-11px) rotate(2deg)' },
        },
        breathe: {
          '0%,100%': { transform: 'translateY(0) scale(1)' },
          '50%': { transform: 'translateY(-12px) scale(1.02)' },
        },
        popin: {
          '0%': { transform: 'rotateY(180deg) scale(.86)' },
          '60%': { transform: 'rotateY(180deg) scale(1.05)' },
          '100%': { transform: 'rotateY(180deg) scale(1)' },
        },
        sweep: {
          from: { backgroundPosition: '190% 0' },
          to: { backgroundPosition: '-90% 0' },
        },
        blink: { '50%': { opacity: '0' } },
        pulse: {
          '0%,100%': { opacity: '.55', letterSpacing: '9px' },
          '50%': { opacity: '1', letterSpacing: '13px' },
        },
        fadeUp: {
          from: { opacity: '0', transform: 'translateY(22px)' },
          to: { opacity: '1', transform: 'none' },
        },
        bobin: {
          from: { opacity: '0', transform: 'translateY(26px) scale(.94)' },
          to: { opacity: '1', transform: 'none' },
        },
        drift: {
          '0%': { transform: 'translateY(20vh) translateX(0) rotate(-4deg)' },
          '50%': { transform: 'translateY(-10vh) translateX(30px) rotate(4deg)' },
          '100%': { transform: 'translateY(-40vh) translateX(0) rotate(-4deg)' },
        },
      },
      animation: {
        squish: `squish 2.4s ${motion.easing} infinite`,
        letterhop: `letterhop 2.6s ${motion.easing} infinite`,
        bob: 'bob 3.4s ease-in-out infinite',
        breathe: 'breathe 2.8s ease-in-out infinite',
        pulse: 'pulse 3s ease-in-out infinite',
        blink: 'blink 1s steps(2) infinite',
        'fade-up': `fadeUp .45s ${motion.easing}`,
        bobin: `bobin .6s ${motion.easing} backwards`,
        sweep: 'sweep 1.3s linear infinite',
      },
    },
  },
} satisfies Partial<Config>;

export default pixelslimePreset;
