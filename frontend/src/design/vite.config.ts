import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev-only harness so W5 can preview the design system in isolation.
// W6 owns the real Vite config at the frontend root.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { outDir: 'dist' },
});
