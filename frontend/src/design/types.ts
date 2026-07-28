/**
 * Shared display types for the PIXELSLIME design system.
 *
 * WHY: these are presentation-oriented types, intentionally decoupled from the
 * wire shapes in contracts/openapi.yaml (`CardSummary`, `Card`). The design
 * system should not depend on the transport layer; W6 maps API responses onto
 * these props (see the design system README for the trivial mapping).
 */

import { rarity, typeColor } from './tokens';

/** The six rarity tiers, keyed exactly as in contracts/card.schema.json. */
export type Rarity = keyof typeof rarity;

/** The sixteen slime types. */
export type SlimeType = keyof typeof typeColor;

/** The four battle stats a card carries. */
export type StatKey = 'strength' | 'endurance' | 'agility' | 'happiness';

/** Procedural sprite accessories, matching the mockup's ACC table. */
export type SlimeAccessory = 'flower' | 'leaf' | 'star' | 'horn' | 'none';

/** Procedural sprite facial expressions. */
export type SlimeFace = 'happy' | 'smug' | 'sleepy';

export const RARITY_ORDER: readonly Rarity[] = [
  'COMMON',
  'UNCOMMON',
  'RARE',
  'EPIC',
  'LEGENDARY',
  'MYTHIC',
];

export const SLIME_TYPES: readonly SlimeType[] = [
  'FAIRY',
  'FOREST',
  'WATER',
  'EMBER',
  'STORM',
  'STONE',
  'SUGAR',
  'GHOST',
  'METAL',
  'COSMIC',
  'BLOOM',
  'FROST',
  'SLUDGE',
  'BEAM',
  'PAPER',
  'DREAM',
];

/**
 * Everything a gallery tile needs to render, and nothing more. Maps directly
 * from the API `CardSummary`: pass `thumbUrl` as `imageSrc`. When no image is
 * available (e.g. a placeholder or an unrevealed silhouette) the procedural
 * sprite fields drive a <SlimeSprite/> fallback.
 */
export interface SlimeCardData {
  serial: number;
  name: string;
  rarity: Rarity;
  type: SlimeType;
  /** Optional; when absent it is derived from `serial` as `PS-0001`. */
  cardId?: string;
  level?: number;
  /** Real artwork (thumbUrl / imageUrl). Falls back to the procedural sprite. */
  imageSrc?: string;
  /** Base colour for the procedural sprite fallback. */
  spriteColor?: string;
  accessory?: SlimeAccessory;
  face?: SlimeFace;
}

/** Render a serial as its canonical `PS-0001` card id. */
export function toCardId(serial: number): string {
  return `PS-${String(serial).padStart(4, '0')}`;
}
