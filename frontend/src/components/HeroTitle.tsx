import type { ReactElement } from 'react';
import {
  AnimatedTitle,
  useReducedMotion,
  useTypewriter,
  type AnimatedTitleProps,
} from '@/design';

export interface HeroTitleProps extends Omit<AnimatedTitleProps, 'subtitle'> {
  /** Subtitle text, rendered accessibly (see below). */
  subtitle: string;
}

/**
 * The hero lockup, wrapped for accessibility.
 *
 * W5's <AnimatedTitle/> renders its subtitle as `<div class="ps-subtitle" aria-label=…>`
 * with the animated copy `aria-hidden` — but aria-label on a role-less <div> is prohibited
 * (axe `aria-prohibited-attr`, serious, on every hero page). Until the design system fixes
 * it, we suppress that subtitle (`subtitle={null}`) and render our own: the typewriter copy
 * stays `aria-hidden` while the full text lives in a visually-hidden `sr-only` span, so the
 * accessible name comes from real text content, not an aria-label on a bare div. Same font,
 * same `.ps-subtitle` styling, same typewriter, same reduced-motion degrade.
 */
export function HeroTitle({ subtitle, typewriter = true, ...rest }: HeroTitleProps): ReactElement {
  const reduced = useReducedMotion();
  const typed = useTypewriter(subtitle, { enabled: typewriter && !reduced });
  return (
    <>
      <AnimatedTitle {...rest} typewriter={typewriter} subtitle={null} />
      <div className="ps-subtitle">
        <span aria-hidden="true">
          {typed}
          <span className="ps-caret">▌</span>
        </span>
        <span className="sr-only">{subtitle}</span>
      </div>
    </>
  );
}

export default HeroTitle;
