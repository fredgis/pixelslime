import type { ReactElement } from 'react';
import { rarity } from '../tokens';
import type { Rarity } from '../types';
import { Chip } from './Chip';

/**
 * <RarityBadge/> — the coloured rarity pill. Shows the tier and its in-world House
 * name (EPIC · Aurora), coloured by the rarity token, with text contrast handled
 * by <Chip/>. `format` trims it down for tight spots (gallery tags use "house").
 */

export interface RarityBadgeProps {
  rarity: Rarity;
  /** `full` = "◈ EPIC · Aurora", `rarity` = "◈ EPIC", `house` = "AURORA". */
  format?: 'full' | 'rarity' | 'house';
  size?: 'sm' | 'md';
  className?: string;
}

export function RarityBadge({
  rarity: tier,
  format = 'full',
  size = 'md',
  className,
}: RarityBadgeProps): ReactElement {
  const info = rarity[tier];
  const label =
    format === 'house'
      ? info.house.toUpperCase()
      : format === 'rarity'
        ? `◈ ${tier}`
        : `◈ ${tier} · ${info.house}`;

  return (
    <Chip
      tone={info.color}
      size={size}
      className={className}
      aria-label={`Rarity ${tier}, ${info.house} house`}
    >
      {label}
    </Chip>
  );
}

export default RarityBadge;
