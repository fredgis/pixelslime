import { useEffect, useState } from 'react';

export interface TypewriterOptions {
  /** Milliseconds per character. */
  speed?: number;
  /** Pause before restarting once the full string is typed, in ms. */
  pause?: number;
  /** Loop forever (true) or type once (false). */
  loop?: boolean;
  /**
   * When false, the full text appears immediately and no timers run. Callers pass
   * `!useReducedMotion()` so the effect honours the motion preference centrally.
   */
  enabled?: boolean;
}

/**
 * Types `text` out one character at a time, exactly like the mockup's subtitle.
 * Returns the substring currently visible. When disabled (reduced motion) it
 * returns the whole string at once — the accessible, no-motion degrade.
 */
export function useTypewriter(text: string, options: TypewriterOptions = {}): string {
  const { speed = 95, pause = 4200, loop = true, enabled = true } = options;
  const [count, setCount] = useState<number>(enabled ? 0 : text.length);

  useEffect(() => {
    if (!enabled) {
      setCount(text.length);
      return;
    }
    setCount(0);
    let timer: ReturnType<typeof setTimeout>;
    let index = 0;

    const step = (): void => {
      setCount(index);
      if (index < text.length) {
        index += 1;
        timer = setTimeout(step, speed);
      } else if (loop) {
        timer = setTimeout(() => {
          index = 0;
          step();
        }, pause);
      }
    };
    step();

    return () => clearTimeout(timer);
  }, [text, speed, pause, loop, enabled]);

  return text.slice(0, count);
}
