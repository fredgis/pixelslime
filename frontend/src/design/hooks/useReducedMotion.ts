import { useEffect, useState } from 'react';

/**
 * The single source of truth for motion preference across the design system.
 *
 * WHY centralised: the brief requires that *every* animation degrades to a fade,
 * implemented once rather than per component. The CSS half lives in globals.css
 * (`@media (prefers-reduced-motion: reduce)`); this hook is the JS half, so that
 * canvas/timer-driven effects (confetti, typewriter, stat fill, pointer tilt)
 * read the exact same signal and short-circuit consistently.
 *
 * SSR-safe: assumes motion is allowed until the browser confirms otherwise.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent): void => setReduced(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return reduced;
}
