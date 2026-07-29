/**
 * Ambient background tint. When today's card is revealed (or a profile is open) the
 * page background adopts the card's dominant palette; this tiny store lets a screen set
 * that tint without prop-drilling through the router Outlet. Layout renders the overlay.
 */
import { create } from 'zustand';

interface AmbientState {
  tint: string | null;
  setTint: (tint: string | null) => void;
}

export const useAmbientStore = create<AmbientState>((set) => ({
  tint: null,
  setTint: (tint) => set({ tint }),
}));
