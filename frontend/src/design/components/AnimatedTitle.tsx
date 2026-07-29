import type { ElementType, ReactNode, ReactElement } from 'react';
import { confettiPalette, color } from '../tokens';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { useTypewriter } from '../hooks/useTypewriter';

/**
 * <AnimatedTitle/> — the hero lockup: a ぷにぷに eyebrow, the wordmark whose every
 * letter bounces on a stagger with squash-and-stretch, and a subtitle that types
 * itself out. On MYTHIC days pass `rainbow` for the animated foil. The decorative
 * per-letter spans and the typewriter copy are `aria-hidden`, and the complete text
 * is exposed once via a visually-hidden `.ps-sr-only` span, so assistive tech reads
 * each line as one whole phrase instead of a character-by-character stutter (and we
 * avoid putting `aria-label` on role-less elements). Reduced motion is honoured
 * centrally.
 */

export interface AnimatedTitleProps {
  /** The wordmark. Defaults to PIXELSLIME. */
  text?: string;
  /** Small line above the wordmark. Pass null to hide. */
  eyebrow?: ReactNode;
  /** Subtitle that types itself out. Pass null to hide. */
  subtitle?: string | null;
  /** Animated rainbow foil for MYTHIC days. */
  rainbow?: boolean;
  /** Type the subtitle out (true) or show it whole (false). */
  typewriter?: boolean;
  /** Heading element to render. Defaults to h1. */
  as?: ElementType;
  className?: string;
}

export function AnimatedTitle({
  text = 'PIXELSLIME',
  eyebrow = '✦ ぷにぷに ✦',
  subtitle = 'PUNIPUNI PARADISE',
  rainbow = false,
  typewriter = true,
  as: Heading = 'h1',
  className,
}: AnimatedTitleProps): ReactElement {
  const reduced = useReducedMotion();
  const typed = useTypewriter(subtitle ?? '', { enabled: typewriter && !reduced });
  const titleClasses = ['ps-title', rainbow ? 'ps-title--rainbow' : '']
    .filter(Boolean)
    .join(' ');
  const rootClasses = ['ps-hero', className ?? ''].filter(Boolean).join(' ');

  return (
    <div className={rootClasses}>
      {eyebrow != null ? <div className="ps-eyebrow">{eyebrow}</div> : null}

      <Heading className={titleClasses}>
        <span className="ps-sr-only">{text}</span>
        {[...text].map((ch, i) => (
          <span
            key={`${ch}-${i}`}
            aria-hidden="true"
            style={{
              color: confettiPalette[i % confettiPalette.length],
              animationDelay: `${i * 0.08}s`,
            }}
          >
            {ch}
          </span>
        ))}
      </Heading>

      {subtitle != null ? (
        <div className="ps-subtitle">
          <span className="ps-sr-only">{subtitle}</span>
          <span aria-hidden="true">
            {typed}
            <span className="ps-caret">▌</span>
          </span>
        </div>
      ) : null}

      <svg
        className="ps-goo"
        width="180"
        height="26"
        viewBox="0 0 180 26"
        aria-hidden="true"
      >
        <path
          d="M0 8 Q30 0 60 8 T120 8 T180 8 L180 26 L0 26Z"
          fill={color.bubblegum}
          opacity="0.28"
        />
      </svg>
    </div>
  );
}

export default AnimatedTitle;
