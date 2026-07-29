/**
 * API → design-system mapping and small display helpers.
 *
 * The design system is deliberately decoupled from the wire types, so this is the one
 * place that turns a {@link CardSummary}/{@link Card} into the {@link SlimeCardData} a
 * tile needs. Procedural sprite hints (colour/accessory/face) are derived deterministically
 * from the serial so silhouettes and fallbacks look varied — the real API does not carry
 * them, and neither does the mock's wire payload, so deriving keeps us contract-faithful.
 */
import type { Card, CardSummary, Rarity, SlimeType } from '@/api/types';
import {
  tokens,
  toCardId,
  type SlimeAccessory,
  type SlimeCardData,
  type SlimeFace,
} from '@/design';

const ACCESSORIES: readonly SlimeAccessory[] = ['flower', 'leaf', 'star', 'horn', 'none'];
const FACES: readonly SlimeFace[] = ['happy', 'smug', 'sleepy'];

function hash32(n: number): number {
  return Math.imul(n ^ 0x9e3779b9, 2654435761) >>> 0;
}

/** Deterministic procedural-sprite hints for a serial — used for silhouettes/fallbacks. */
export function spriteHints(serial: number, type: SlimeType): {
  spriteColor: string;
  accessory: SlimeAccessory;
  face: SlimeFace;
} {
  const h = hash32(serial);
  return {
    spriteColor: tokens.typeColor[type],
    accessory: ACCESSORIES[h % ACCESSORIES.length],
    face: FACES[(h >>> 5) % FACES.length],
  };
}

/** Map an API card (summary or full) onto the design system's tile data. */
export function toSlimeCardData(card: CardSummary | Card): SlimeCardData {
  const hints = spriteHints(card.serial, card.type);
  return {
    serial: card.serial,
    name: card.name,
    rarity: card.rarity,
    type: card.type,
    cardId: card.cardId,
    level: card.level,
    imageSrc: card.thumbUrl,
    ...hints,
  };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Format a `YYYY-MM-DD` mint date as `29 Jul 2026`, timezone-safe. */
export function formatMintDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** Rarity metadata straight from the design tokens (house, colour, yield, price). */
export function rarityInfo(rarity: Rarity) {
  return tokens.rarity[rarity];
}

/** The card's dominant colours, falling back to rarity+type hues when absent. */
export function dominantPalette(card: Card): [string, string, string] {
  const p = card.palette ?? [];
  return [
    p[0] ?? tokens.typeColor[card.type],
    p[1] ?? tokens.rarity[card.rarity].color,
    p[2] ?? tokens.color.grape,
  ];
}

/** A soft radial-gradient background string tinted to a card's palette. */
export function paletteBackground(card: Card): string {
  const [a, b] = dominantPalette(card);
  return (
    `radial-gradient(1100px 620px at 22% -8%, ${a}55, transparent 60%),` +
    `radial-gradient(900px 560px at 92% 4%, ${b}44, transparent 58%)`
  );
}

export { toCardId };
