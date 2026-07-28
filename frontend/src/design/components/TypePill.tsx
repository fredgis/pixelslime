import type { ReactNode, ReactElement } from 'react';
import { typeColor } from '../tokens';
import type { SlimeType } from '../types';
import { Chip } from './Chip';

/**
 * <TypePill/> — a slime type as a coloured pill (FAIRY, COSMIC…). Coloured by the
 * type token with automatic AA-legible text. An optional icon adds flavour, as on
 * the mockup's "💗 FAIRY" chip.
 */

export interface TypePillProps {
  type: SlimeType;
  icon?: ReactNode;
  size?: 'sm' | 'md';
  className?: string;
}

export function TypePill({ type, icon, size = 'md', className }: TypePillProps): ReactElement {
  return (
    <Chip
      tone={typeColor[type]}
      icon={icon}
      size={size}
      className={className}
      aria-label={`Type ${type}`}
    >
      {type}
    </Chip>
  );
}

export default TypePill;
