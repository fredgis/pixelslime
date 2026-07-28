import { forwardRef, useImperativeHandle, useRef } from 'react';
import type { ReactElement } from 'react';
import { useConfetti } from '../hooks/useConfetti';
import type { ConfettiOrigin } from '../hooks/useConfetti';
import { useReducedMotion } from '../hooks/useReducedMotion';

/**
 * <Confetti/> — the full-screen canvas burst from the mockup. Mount it once near the
 * app root and fire it imperatively via a ref on a joyful moment (an EPIC reveal, a
 * secret unlock). The rAF loop lives in useConfetti and is torn down on unmount, so
 * there is never a leaked animation frame. Respects reduced motion: `fire()` is a
 * no-op when the user prefers less movement.
 */

export interface ConfettiHandle {
  fire: (origin?: ConfettiOrigin) => void;
}

export interface ConfettiProps {
  colors?: readonly string[];
  /** Pieces per burst. Defaults to 140. */
  count?: number;
  className?: string;
}

export const Confetti = forwardRef<ConfettiHandle, ConfettiProps>(function Confetti(
  { colors, count, className },
  ref,
): ReactElement {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  const { fire } = useConfetti(canvasRef, { colors, count, enabled: !reduced });

  useImperativeHandle(ref, () => ({ fire }), [fire]);

  const classes = ['ps-confetti', className ?? ''].filter(Boolean).join(' ');
  return <canvas ref={canvasRef} className={classes} aria-hidden="true" />;
});

export default Confetti;
