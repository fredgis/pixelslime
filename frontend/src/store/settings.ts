/**
 * Settings store — the two visitor preferences that persist across visits.
 *
 * `theme` flips the design system's day/MOONLIT-PUNIVERSE palette by setting
 * `document.documentElement.dataset.theme` (see applyTheme in the app shell). Reduced
 * motion is intentionally NOT here: the design system reads the OS `prefers-reduced-motion`
 * media query via useReducedMotion, and we must not reinvent it.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Theme = 'day' | 'night';

interface SettingsState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      theme: 'day',
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((state) => ({ theme: state.theme === 'day' ? 'night' : 'day' })),
    }),
    { name: 'pixelslime.settings', version: 1 },
  ),
);
