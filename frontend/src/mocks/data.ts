/**
 * The mock's seed collection: 14 cards, serial 1 (oldest) → 14 (today's bloom).
 *
 * Three carry genuine AI-generated artwork (Nimbusnooze, Mochibo, Thundersnuggle —
 * their stats come verbatim from backend/tests/ai/output and contracts/cards/mochibo.json);
 * the other eleven are the mockup's procedural slimes, rendered as self-contained SVG
 * data-URIs. Today's card (serial 14) is Thundersnuggle LEGENDARY, so the reveal shows
 * the ≥EPIC confetti-and-shake ceremony.
 *
 * Everything the API returns is derived from this table, so the mock never drifts from
 * the shape in contracts/openapi.yaml. Provenance rows are computed with real Z85 and a
 * real keccak-256 anchor (see ./psc).
 */
import type { Card, CardSummary, Rarity, SlimeType } from '@/api/types';
import type { RawResponse } from '@/api/types';
import { tokens } from '@/design';
import { keccak256, z85Encode } from './psc';
import { mockCardSvg, svgDataUri, pseudoArtId, type MockAccessory, type MockFace } from './sprite';

/**
 * The frozen lookup tables from contracts/lookups.json — biome/mood/companion display
 * names, resolved by W7 from the ids packed into the PSC-1 header. The tables are
 * append-only (ids are list indices that never reorder), so mirroring the current
 * values here keeps the mock's resolved names identical to what the real API returns.
 * Typing the seeds against these unions makes any name that is NOT in the frozen table
 * a compile error, so the mock cannot silently drift from the contract.
 */
const BIOMES = [
  'Open Meadow', 'Sunlit Forest', 'Tide Pool Cove', 'Cozy Bedroom', 'Cozy Reading Room',
  'Rainy Street', 'Cluttered Workshop', 'Library at Dusk', 'Mushroom Grove', 'Snowy Village',
  'Candy Kitchen', 'Starlit Rooftop', 'Rockpool Cavern', 'Sunny Greenhouse', 'Arcade Corner',
  'Cloud Terrace',
] as const;
const MOODS = [
  'Cheerful', 'Sleepy', 'Curious', 'Mischievous', 'Serene',
  'Excited', 'Bashful', 'Determined', 'Dreamy', 'Grumpy',
] as const;
const COMPANIONS = [
  'Sleepy Puff Cat', 'Tiny Sparrow', 'Bumble Bee Buddy', 'Pebble Crab', 'Glow Moth',
  'Acorn Squirrel', 'Paper Crane', 'Bubble Fish', 'Clover Bunny', 'Ember Pup',
  'Frost Fawn', 'Star Tadpole',
] as const;
type Biome = (typeof BIOMES)[number];
type Mood = (typeof MOODS)[number];
type Companion = (typeof COMPANIONS)[number];

/**
 * Serials still awaiting on-chain anchoring: their `chain` is `null` and `onChain` is
 * false, so the profile badge, the SLIMEDEX and the SMILE BANK anchor list all exercise
 * the "not yet anchored" path exactly as the contract models it (chain present-but-null).
 */
const PENDING_ANCHOR = new Set<number>([8, 11]);

interface Seed {
  name: string;
  level: number;
  rarity: Rarity;
  type: SlimeType;
  height_mm: number;
  weight_g: number;
  strength: number;
  endurance: number;
  agility: number;
  happiness: number;
  personality: string;
  power_name: string;
  power_desc: string;
  quote: string;
  biome: Biome;
  mood: Mood;
  companion: Companion | null;
  spriteColor: string;
  accessory: MockAccessory;
  face: MockFace;
  /** Key into public/mock/<key>-{512,1024}.webp when the card has real artwork. */
  art?: string;
  shiny?: boolean;
  palette?: string[];
}

/** Ordered oldest → newest; array index + 1 becomes the serial. */
const SEEDS: readonly Seed[] = [
  {
    name: 'Fernwick', level: 8, rarity: 'COMMON', type: 'FOREST',
    height_mm: 210, weight_g: 640, strength: 34, endurance: 48, agility: 39, happiness: 72,
    personality: 'Quiet and patient. Naps under ferns and hums to beetles.',
    power_name: 'Moss Hug', power_desc: 'Wraps a friend in warm moss, blocking the next hit.',
    quote: 'Puni… (five more minutes)', biome: 'Mushroom Grove', mood: 'Sleepy', companion: 'Acorn Squirrel',
    spriteColor: '#7FCB93', accessory: 'leaf', face: 'sleepy',
  },
  {
    name: 'Blorbit', level: 19, rarity: 'LEGENDARY', type: 'COSMIC',
    height_mm: 340, weight_g: 1180, strength: 61, endurance: 70, agility: 88, happiness: 90,
    personality: 'Dreamy stargazer. Hums the sound of a distant satellite.',
    power_name: 'Orbit Drop', power_desc: 'Calls a tiny meteor of pure glitter onto the field.',
    quote: 'Blorb! (I saw the whole sky!)', biome: 'Starlit Rooftop', mood: 'Dreamy', companion: 'Glow Moth',
    spriteColor: '#7C6BE0', accessory: 'star', face: 'happy',
  },
  {
    name: 'Puddington', level: 5, rarity: 'UNCOMMON', type: 'WATER',
    height_mm: 190, weight_g: 520, strength: 18, endurance: 41, agility: 57, happiness: 84,
    personality: 'Polite little puddle. Apologises for being damp.',
    power_name: 'Splish Bow', power_desc: 'A courteous splash that slows everyone nearby.',
    quote: 'Plip! (Terribly sorry.)', biome: 'Rainy Street', mood: 'Bashful', companion: 'Bubble Fish',
    spriteColor: '#63BEEA', accessory: 'none', face: 'happy',
  },
  {
    name: 'Kinaco', level: 14, rarity: 'RARE', type: 'SUGAR',
    height_mm: 250, weight_g: 810, strength: 31, endurance: 52, agility: 60, happiness: 91,
    personality: 'Smells of toasted soybean flour. Extremely proud of it.',
    power_name: 'Dust Bloom', power_desc: 'A sweet cloud that makes opponents sneeze politely.',
    quote: 'Kina! (Taste the sunshine!)', biome: 'Candy Kitchen', mood: 'Cheerful', companion: 'Clover Bunny',
    spriteColor: '#F3C98B', accessory: 'none', face: 'smug',
  },
  {
    name: 'Ashmallow', level: 11, rarity: 'RARE', type: 'EMBER',
    height_mm: 230, weight_g: 700, strength: 52, endurance: 44, agility: 47, happiness: 66,
    personality: 'Warm, slightly singed, always a little too close to the fire.',
    power_name: 'Toast Puff', power_desc: 'Puffs up golden-brown and radiates cosy heat.',
    quote: 'Fwoosh! (Perfectly toasted.)', biome: 'Sunny Greenhouse', mood: 'Serene', companion: 'Ember Pup',
    spriteColor: '#FF9264', accessory: 'none', face: 'happy',
  },
  {
    name: 'Nibblewisp', level: 16, rarity: 'EPIC', type: 'GHOST',
    height_mm: 270, weight_g: 430, strength: 24, endurance: 38, agility: 93, happiness: 58,
    personality: 'Shy haunting. Steals biscuits, always leaves a thank-you note.',
    power_name: 'Crumb Fade', power_desc: 'Vanishes into crumbs, reappearing behind the target.',
    quote: '…hi. (sorry about the biscuits)', biome: 'Library at Dusk', mood: 'Bashful', companion: null,
    spriteColor: '#B6ADE2', accessory: 'horn', face: 'sleepy',
  },
  {
    name: 'Glimmerpuff', level: 22, rarity: 'MYTHIC', type: 'DREAM',
    height_mm: 310, weight_g: 660, strength: 44, endurance: 63, agility: 79, happiness: 99,
    personality: 'A dream that got lost on the way to someone. Very apologetic.',
    power_name: 'Lullabloom', power_desc: 'Everyone nearby takes a short, extremely good nap.',
    quote: 'Shhh… (you are almost there)', biome: 'Cloud Terrace', mood: 'Dreamy', companion: 'Star Tadpole',
    spriteColor: '#FFA8DE', accessory: 'star', face: 'happy',
  },
  {
    name: 'Cobblenop', level: 7, rarity: 'COMMON', type: 'STONE',
    height_mm: 200, weight_g: 1500, strength: 58, endurance: 77, agility: 14, happiness: 61,
    personality: 'Heavy, dependable, absolutely refuses to hurry.',
    power_name: 'Sit Down', power_desc: 'Sits. Nothing moves it. That is the whole move.',
    quote: '…nope. (I live here now)', biome: 'Open Meadow', mood: 'Grumpy', companion: 'Pebble Crab',
    spriteColor: '#A79684', accessory: 'none', face: 'smug',
  },
  {
    name: 'Zapkin', level: 13, rarity: 'UNCOMMON', type: 'STORM',
    height_mm: 240, weight_g: 590, strength: 47, endurance: 40, agility: 81, happiness: 74,
    personality: 'Overcaffeinated cloudlet. Vibrates when excited, which is always.',
    power_name: 'Static Boop', power_desc: 'A tiny shock that makes everyone’s hair stand up.',
    quote: 'BZZT! (did you feel that?!)', biome: 'Arcade Corner', mood: 'Excited', companion: 'Tiny Sparrow',
    spriteColor: '#9B87F0', accessory: 'none', face: 'happy',
  },
  {
    name: 'Origamew', level: 9, rarity: 'RARE', type: 'PAPER',
    height_mm: 220, weight_g: 120, strength: 21, endurance: 29, agility: 86, happiness: 80,
    personality: 'Folds itself into whatever shape the moment requires.',
    power_name: 'Crease Step', power_desc: 'Folds flat, slips through the gap, unfolds behind you.',
    quote: 'Kami! (fold me again!)', biome: 'Cluttered Workshop', mood: 'Curious', companion: 'Paper Crane',
    spriteColor: '#EFDFBE', accessory: 'none', face: 'happy',
  },
  {
    name: 'Frostbun', level: 15, rarity: 'EPIC', type: 'FROST',
    height_mm: 260, weight_g: 880, strength: 36, endurance: 68, agility: 55, happiness: 87,
    personality: 'Cold on the outside, suspiciously warm in the middle.',
    power_name: 'Snow Nap', power_desc: 'Freezes the ground into a soft, extremely comfy drift.',
    quote: 'Fuwa! (still warm inside!)', biome: 'Snowy Village', mood: 'Serene', companion: 'Frost Fawn',
    spriteColor: '#A9E4F2', accessory: 'none', face: 'happy',
  },
  {
    name: 'Nimbusnooze', level: 14, rarity: 'COMMON', type: 'COSMIC',
    height_mm: 238, weight_g: 684, strength: 22, endurance: 47, agility: 31, happiness: 78,
    personality: 'A drowsy stargazer who naps on clouds and trusts its paper crane to navigate.',
    power_name: 'Crane Constellation',
    power_desc: 'Its paper crane traces sleepy stars that wrap nearby friends in calming light.',
    quote: 'Wake me when the stars twinkle.', biome: 'Cloud Terrace', mood: 'Dreamy', companion: 'Paper Crane',
    spriteColor: '#8FD3FF', accessory: 'none', face: 'sleepy',
    art: 'nimbusnooze', palette: ['#8FD3FF', '#B6ADE2', '#FFF3D6'],
  },
  {
    name: 'Mochibo', level: 12, rarity: 'EPIC', type: 'FAIRY',
    height_mm: 280, weight_g: 900, strength: 28, endurance: 55, agility: 65, happiness: 95,
    personality: 'Sweet and cuddly. Loves cozy places and spreading joy!',
    power_name: 'Sugar Squish', power_desc: 'Covers the area in sweet goo, healing allies over time.',
    quote: 'Mochi! (Hugs all around!)', biome: 'Cozy Reading Room', mood: 'Cheerful', companion: 'Sleepy Puff Cat',
    spriteColor: '#FF9EC4', accessory: 'flower', face: 'happy',
    art: 'mochibo', palette: ['#FF9EC4', '#FFD86B', '#8FD3FF'],
  },
  {
    name: 'Thundersnuggle', level: 88, rarity: 'LEGENDARY', type: 'STORM',
    height_mm: 274, weight_g: 1260, strength: 72, endurance: 84, agility: 91, happiness: 96,
    personality: 'Curious and cozy, it investigates every creak while its Puff Cat naps nearby.',
    power_name: 'Blanket Thunder',
    power_desc: 'Summons a warm storm cloud that zaps foes and tucks allies into crackling blankets.',
    quote: 'Was that thunder under the bed?', biome: 'Cozy Bedroom', mood: 'Curious', companion: 'Sleepy Puff Cat',
    spriteColor: '#8B6FE8', accessory: 'star', face: 'happy',
    art: 'thundersnuggle', palette: ['#8B6FE8', '#FFD86B', '#5FB8E8'],
  },
];

/** Serial of the current daily bloom. */
export const TODAY_SERIAL = SEEDS.length;

const MINT_DATES = buildMintDates(SEEDS.length, '2026-07-29');

function buildMintDates(count: number, latest: string): string[] {
  const end = new Date(`${latest}T00:00:00Z`);
  const out: string[] = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(end);
    d.setUTCDate(end.getUTCDate() - (count - 1 - i));
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function cardIdFor(serial: number): string {
  return `PS-${String(serial).padStart(4, '0')}`;
}

function paletteFor(seed: Seed): string[] {
  if (seed.palette) return seed.palette;
  return [seed.spriteColor, tokens.typeColor[seed.type], tokens.rarity[seed.rarity].color];
}

function thumbUrlFor(seed: Seed, serial: number): string {
  if (seed.art) return `/mock/${seed.art}-512.webp`;
  return svgDataUri(procSvg(seed, serial));
}

function imageUrlFor(seed: Seed, serial: number): string {
  if (seed.art) return `/mock/${seed.art}-1024.webp`;
  return svgDataUri(procSvg(seed, serial));
}

function procSvg(seed: Seed, _serial: number): string {
  return mockCardSvg({
    baseColor: seed.spriteColor,
    accessory: seed.accessory,
    face: seed.face,
    rarityColor: tokens.rarity[seed.rarity].color,
  });
}

/** All cards, fully decoded, serial ascending. */
export const CARDS: readonly Card[] = SEEDS.map((seed, i) => {
  const serial = i + 1;
  const txHash = keccak256(new TextEncoder().encode(`${cardIdFor(serial)}:anchor`));
  const chain = PENDING_ANCHOR.has(serial)
    ? null
    : {
        tokenId: serial,
        txHash,
        blockNumber: 8_100_000 + serial * 137,
        explorerUrl: `https://amoy.polygonscan.com/tx/${txHash}`,
      };
  return {
    serial,
    cardId: cardIdFor(serial),
    name: seed.name,
    level: seed.level,
    rarity: seed.rarity,
    rarityHouse: tokens.rarity[seed.rarity].house,
    type: seed.type,
    shiny: seed.shiny ?? false,
    height_mm: seed.height_mm,
    weight_g: seed.weight_g,
    strength: seed.strength,
    endurance: seed.endurance,
    agility: seed.agility,
    happiness: seed.happiness,
    personality: seed.personality,
    power_name: seed.power_name,
    power_desc: seed.power_desc,
    quote: seed.quote,
    biome: seed.biome,
    mood: seed.mood,
    companion: seed.companion,
    mintDate: MINT_DATES[i],
    dayNumber: serial,
    imageUrl: imageUrlFor(seed, serial),
    thumbUrl: thumbUrlFor(seed, serial),
    palette: paletteFor(seed),
    onChain: chain != null,
    chain,
  } satisfies Card;
});

export const CARDS_BY_SERIAL: ReadonlyMap<number, Card> = new Map(CARDS.map((c) => [c.serial, c]));

export function toSummary(card: Card): CardSummary {
  return {
    serial: card.serial,
    cardId: card.cardId,
    name: card.name,
    level: card.level,
    rarity: card.rarity,
    type: card.type,
    shiny: card.shiny,
    mintDate: card.mintDate,
    thumbUrl: card.thumbUrl,
    onChain: card.onChain ?? (card.chain != null),
  };
}

export const SUMMARIES: readonly CardSummary[] = CARDS.map(toSummary);

/* ───────────────────────── provenance ───────────────────────── */

/**
 * asmDB stores at most 175 bytes of Z85 text per row, which is floor(175 / 5) × 4 = 140
 * binary stream bytes. A PSC-1 card is a short run of such rows (≤ 4 rows / 560 bytes).
 * 175 is the capacity of ONE row — never the size of a card.
 */
const ROW_CAPACITY_BYTES = 140;

/**
 * Real PSC-1 streams are VARIABLE length. These are the measured sizes of the reference
 * cards (docs/CODEC.md §5, confirmed by W10 against the real backend): Mochibo packs into
 * a 52-byte single row; the LEGENDARY Thundersnuggle needs 183 bytes across two. Every
 * other serial derives a realistic length from its own copy, so the mock never pretends
 * every card is the same size (the bug W10 caught: it used to pad every card to 175).
 */
const STREAM_BYTES_BY_SERIAL: Readonly<Record<number, number>> = { 13: 52, 14: 183 };

/** A card's PSC-1 stream length: the measured reference value, or a realistic derivation. */
function streamBytesFor(card: Card): number {
  const measured = STREAM_BYTES_BY_SERIAL[card.serial];
  if (measured !== undefined) return measured;
  const body = [card.name, card.personality, card.power_name, card.power_desc, card.quote].join(
    '\u001f',
  );
  const bodyBytes = new TextEncoder().encode(body).length;
  // 32-byte binary header + dictionary-compressed body (the real codec saves ~45%).
  const total = 32 + Math.round(bodyBytes * 0.55);
  return Math.max(44, Math.min(total, ROW_CAPACITY_BYTES * 4));
}

/**
 * A card's deterministic PSC-1 byte stream at its real (variable) length. The bytes are
 * seeded from the card's own fields, so they are stable and unique per card, and look
 * like the compressed binary the real codec emits once Z85-encoded — no decodable
 * structure, exactly like the real payload.
 */
function streamFor(card: Card): Uint8Array {
  const total = streamBytesFor(card);
  const seed =
    `PSC1|${card.cardId}|${card.name}|${card.rarity}|${card.type}|L${card.level}|` +
    `${card.strength}.${card.endurance}.${card.agility}.${card.happiness}|` +
    `${card.biome ?? '?'}~${card.mood ?? '?'}~${card.companion ?? 'solo'}|` +
    `${card.power_name}|${card.quote}|${pseudoArtId(card.serial)}`;
  const out = new Uint8Array(total);
  // A tiny deterministic PRNG (FNV-seeded LCG) — stable per card, but noise-like.
  let state = 0x811c9dc5;
  for (const b of new TextEncoder().encode(seed)) state = Math.imul(state ^ b, 0x01000193) >>> 0;
  for (let i = 0; i < total; i += 1) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    out[i] = (state >>> 24) & 0xff;
  }
  return out;
}

/**
 * Build the raw provenance view — genuine Z85 rows, the real variable stream length, and a
 * real keccak-256 anchor. Row values follow docs/CODEC.md §4.2: part 0 carries the mint
 * date as YYYYMMDD (positive — the only filterable key), and every continuation row carries
 * -(serial × 16 + part) (negative), so a RANGE query for a day's header row can never pull
 * a continuation row. The header value is what makes the daily-card lookup work.
 */
export function buildRaw(card: Card): RawResponse {
  const stream = streamFor(card);
  const dateKey = card.mintDate.replace(/-/g, '');
  const partCount = Math.max(1, Math.ceil(stream.length / ROW_CAPACITY_BYTES));
  const rows = Array.from({ length: partCount }, (_unused, part) => {
    const piece = stream.subarray(part * ROW_CAPACITY_BYTES, (part + 1) * ROW_CAPACITY_BYTES);
    return {
      id: String(card.serial * 16 + part),
      value: part === 0 ? dateKey : String(-(card.serial * 16 + part)),
      tag: `psc.${card.serial}.${part}`,
      content: z85Encode(piece),
    };
  });
  return {
    rows,
    streamBytes: stream.length,
    rowCount: rows.length,
    cardHash: keccak256(stream),
    decoded: card,
  };
}
