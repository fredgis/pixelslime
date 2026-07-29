/**
 * Renders the toast queue, bottom-centre, in the pixel font. Slide-in is disabled
 * under reduced motion.
 */
import type { ReactElement } from 'react';
import { useReducedMotion } from '@/design';
import { useToastStore } from '@/store/toast';

export function Toaster(): ReactElement {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);
  const reduced = useReducedMotion();

  return (
    <div
      className="fixed inset-x-0 bottom-5 z-50 flex flex-col items-center gap-2 px-4"
      aria-live="polite"
      role="status"
    >
      {toasts.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto flex items-center gap-2 rounded-pill border-4 border-ink bg-ink px-4 py-2 font-pixel text-[10px] text-cream shadow-chunk ${
            reduced ? '' : 'animate-bobin'
          }`}
        >
          {t.icon ? <span aria-hidden>{t.icon}</span> : null}
          <span>{t.message}</span>
        </button>
      ))}
    </div>
  );
}

export default Toaster;
