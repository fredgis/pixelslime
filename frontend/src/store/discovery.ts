/**
 * Discovery store — the Pokédex mechanic.
 *
 * The site has no account and sends nothing about a visitor to the server, so "which
 * slimes have I opened?" lives purely in localStorage. Undiscovered cards render as
 * dark "???" silhouettes in the SLIMEDEX; opening a profile or revealing today's card
 * discovers it. A first-time visitor starts with the three showcase slimes already
 * discovered, so the gallery greets them with real artwork rather than a wall of
 * silhouettes while still demonstrating the mechanic on everything else.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** Cards a brand-new visitor starts with already revealed (the real-artwork trio). */
const SEED_DISCOVERED = [12, 13, 14];

interface DiscoveryState {
  discovered: number[];
  discover: (serial: number) => void;
  isDiscovered: (serial: number) => boolean;
  reset: () => void;
}

export const useDiscoveryStore = create<DiscoveryState>()(
  persist(
    (set, get) => ({
      discovered: SEED_DISCOVERED,
      discover: (serial) =>
        set((state) =>
          state.discovered.includes(serial)
            ? state
            : { discovered: [...state.discovered, serial] },
        ),
      isDiscovered: (serial) => get().discovered.includes(serial),
      reset: () => set({ discovered: [] }),
    }),
    { name: 'pixelslime.discovery', version: 1 },
  ),
);

/** Count of distinct discovered serials — handy for progress read-outs. */
export const selectDiscoveredCount = (state: DiscoveryState): number => state.discovered.length;
