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

  return (
    <span className={classes} style={{ ...toned, ...style }} aria-label={rest['aria-label']}>
      {icon != null ? <span aria-hidden="true">{icon}</span> : null}
      {children}
    </span>
  );
}

export default Chip;
