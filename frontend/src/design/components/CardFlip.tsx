import { useState } from 'react';
import type { ReactNode, ReactElement } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

/**
 * <CardFlip/> — the face-down pixel card back that flips in 3D to reveal the
 * artwork. This is the emotional centrepiece of TODAY'S BLOOM, so it is built to
 * feel good: a breathing, pulsing back that begs to be tapped, then a springy
 * reveal. It is a real <button>, so it is reachable and operable by keyboard
 * (Enter/Space) with a visible focus ring. Under reduced motion the 3D spin becomes
 * a quiet crossfade. Controlled (`revealed`) or uncontrolled (`defaultRevealed`).
 */

export interface CardFlipProps {
  /** Revealed-face content. Ignored when `imageSrc` is given. */
  children?: ReactNode;
  /** Convenience: render an <img> as the revealed face. */
  imageSrc?: string;
  imageAlt?: string;
  /** Controlled reveal state. Omit to let the component manage it. */
  revealed?: boolean;
  /** Initial state when uncontrolled. */
  defaultRevealed?: boolean;
  /** Fired the first time the card is revealed. */
  onReveal?: () => void;
  /** Small seal text on the card back. */
  seal?: ReactNode;
  /** Prompt shown on the card back. */
  hint?: ReactNode;
  /** Accessible name for the revealed card (e.g. the slime's name). */
  revealedLabel?: string;
  className?: string;
}

export function CardFlip({
  children,
  imageSrc,
  imageAlt = '',
  revealed,
  defaultRevealed = false,
  onReveal,
  seal = '✦ PIXEL RAIN ✦',
  hint = 'CLICK TO REVEAL',
  revealedLabel = 'Slime card revealed',
  className,
}: CardFlipProps): ReactElement {
  const reduced = useReducedMotion();
  const isControlled = revealed !== undefined;
  const [internal, setInternal] = useState<boolean>(defaultRevealed);
  const isRevealed = isControlled ? revealed : internal;

  const reveal = (): void => {
    if (isRevealed) return;
    if (!isControlled) setInternal(true);
    onReveal?.();
  };

  const stageClasses = [
    'ps-flipstage',
    isRevealed ? 'revealed' : '',
    reduced ? 'ps-flipstage--reduced' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  const back = imageSrc ? <img src={imageSrc} alt={imageAlt} /> : children;

  return (
    <div className={stageClasses}>
      <button
        type="button"
        className="ps-flipper"
        onClick={reveal}
        aria-label={isRevealed ? revealedLabel : 'Reveal today’s slime card'}
      >
        <div className="ps-face ps-face--front" aria-hidden={isRevealed}>
          <div className="ps-seal">{seal}</div>
          <div className="ps-qm">?</div>
          <div className="ps-hint">{hint}</div>
        </div>
        <div className="ps-face ps-face--back" aria-hidden={!isRevealed}>
          {back}
        </div>
      </button>
    </div>
  );
}

export default CardFlip;
