import type { Config } from 'tailwindcss';
import { pixelslimePreset } from './src/design/tailwind.preset';

/**
 * The app Tailwind config registers the W5 preset (all brand/rarity/type colours,
 * radii, shadows, easing, fonts and keyframes) and points the content globs at the
 * app source plus the design system, so utility classes used in either are kept.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}', '!./src/**/node_modules/**'],
  presets: [pixelslimePreset],
} satisfies Config;
