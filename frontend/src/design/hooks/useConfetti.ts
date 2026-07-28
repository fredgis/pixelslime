import { useCallback, useEffect, useRef } from 'react';
import { confettiPalette } from '../tokens';

interface ConfettiBit {
  x: number;
  y: number;
  vx: number;
  vy: number;
  s: number;
  c: string;
  r: number;
  life: number;
}

export interface ConfettiOrigin {
  /** 0–1 fraction of viewport width. */
  x?: number;
  /** 0–1 fraction of viewport height. */
  y?: number;
}

export interface UseConfettiOptions {
  colors?: readonly string[];
  /** Number of pieces per burst. */
  count?: number;
  /** False makes `fire()` a no-op (reduced motion). */
  enabled?: boolean;
}

export interface ConfettiController {
  /** Launch a burst from `origin` (defaults to the mockup's 28%/45% spot). */
  fire: (origin?: ConfettiOrigin) => void;
}

/**
 * The canvas confetti burst from the mockup, extracted into a reusable hook.
 *
 * WHY a hook: the rAF loop and its lifecycle (start on first burst, stop when the
 * last piece dies, cancel on unmount) is fiddly and must never leak a running
 * animation frame. Centralising it here means <Confetti/> — and any future caller
 * — cannot get that wrong. Honours reduced motion: when disabled, nothing fires.
 */
export function useConfetti(
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  options: UseConfettiOptions = {},
): ConfettiController {
  const { colors = confettiPalette, count = 140, enabled = true } = options;
  const bitsRef = useRef<ConfettiBit[]>([]);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const size = (): void => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    size();
    window.addEventListener('resize', size);
    return () => {
      window.removeEventListener('resize', size);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      bitsRef.current = [];
    };
  }, [canvasRef]);

  const tick = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) {
      rafRef.current = null;
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    bitsRef.current = bitsRef.current.filter((b) => (b.life -= 1) > 0);
    for (const b of bitsRef.current) {
      b.x += b.vx;
      b.y += b.vy;
      b.vy += 0.42;
      b.vx *= 0.99;
      b.r += 0.13;
      ctx.save();
      ctx.translate(b.x, b.y);
      ctx.rotate(b.r);
      ctx.fillStyle = b.c;
      ctx.globalAlpha = Math.min(1, b.life / 45);
      ctx.fillRect(-b.s / 2, -b.s / 2, b.s, b.s);
      ctx.restore();
    }
    if (bitsRef.current.length > 0) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      rafRef.current = null;
    }
  }, [canvasRef]);

  const fire = useCallback(
    (origin: ConfettiOrigin = {}) => {
      if (!enabled) return;
      const { x = 0.28, y = 0.45 } = origin;
      const ox = window.innerWidth * x;
      const oy = window.innerHeight * y;
      for (let i = 0; i < count; i += 1) {
        bitsRef.current.push({
          x: ox,
          y: oy,
          vx: (Math.random() - 0.5) * 17,
          vy: Math.random() * -15 - 4,
          s: 5 + Math.random() * 8,
          c: colors[i % colors.length],
          r: Math.random() * 6,
          life: 150,
        });
      }
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(tick);
    },
    [colors, count, enabled, tick],
  );

  return { fire };
}
