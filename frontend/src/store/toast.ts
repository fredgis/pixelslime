/**
 * Tiny toast queue. The mockup pops a pixel toast for copies, the Konami code, etc.
 * Toasts auto-expire; the <Toaster/> renders them and honours reduced motion.
 */
import { create } from 'zustand';

export interface Toast {
  id: number;
  message: string;
  icon?: string;
}

interface ToastState {
  toasts: Toast[];
  push: (message: string, icon?: string) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (message, icon) => {
    const id = nextId++;
    set((state) => ({ toasts: [...state.toasts, { id, message, icon }] }));
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    }, 2800);
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/** Fire a toast without subscribing a component to the store. */
export function toast(message: string, icon?: string): void {
  useToastStore.getState().push(message, icon);
}
