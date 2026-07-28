import type { Config } from 'tailwindcss';
import { pixelslimePreset } from './tailwind.preset';

// Dev-only Tailwind config for the preview harness. It demonstrates exactly what
// W6 must do at the app root: register `pixelslimePreset`.
export default {
  content: ['./index.html', './preview.tsx', './preview.entry.tsx', './components/**/*.tsx'],
  presets: [pixelslimePreset],
} satisfies Config;
