import type { CSSProperties, ReactNode, ReactElement } from 'react';
import { color } from '../tokens';
import { readableText } from '../lib/color';

/**
 * <Chip/> — the base kawaii pill used everywhere small facts live (level, height,
 * biome…). A coloured `tone` picks its own AA-legible text colour automatically.
 * <RarityBadge/> and <TypePill/> build on this so every pill looks like one family.
 */

export interface ChipProps {
  children: ReactNode;
  /** Fill colour. When omitted the chip is paper with ink text. */
  tone?: string;
  /** Optional leading glyph/emoji; hidden from assistive tech. */
  icon?: ReactNode;
  size?: 'sm' | 'md';
  /** Accessible label when the chip's meaning is not obvious from its text. */
  'aria-label'?: string;
  className?: string;
  style?: CSSProperties;
}

export function Chip({
  children,
  tone,
  icon,
  size = 'md',
  className,
  style,
  ...rest
}: ChipProps): ReactElement {
  const toned: CSSProperties = tone
    ? { background: tone, color: readableText(tone, color.ink, color.paper) }
    : {};
  const classes = ['ps-chip', size === 'sm' ? 'ps-chip--sm' : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  // A bare <span> maps to the generic role, on which `aria-label` is name-prohibited
  // (axe: aria-prohibited-attr). When a label is supplied we promote the pill to
  // role="img" so it is announced as one labelled unit (e.g. "Rarity EPIC, Aurora
  // house") instead of its decorative glyph being read out character by character.
  const label = rest['aria-label'];

  return (
    <span
      className={classes}
      style={{ ...toned, ...style }}
      role={label != null ? 'img' : undefined}
      aria-label={label}
    >
      {icon != null ? <span aria-hidden="true">{icon}</span> : null}
      {children}
    </span>
  );
}

export default Chip;
