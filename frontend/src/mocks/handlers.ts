/**
 * MSW request handlers — one per operation in contracts/openapi.yaml.
 *
 * The mock is generated from the same contract W7 implements, so responses are built
 * from the typed {@link Card}/{@link CardSummary} shapes and validated by the compiler.
 * Loaded only when VITE_USE_MOCK is on (see src/main.tsx), so it never ships in a build
 * that points at the real API.
 */
import { http, HttpResponse, delay } from 'msw';
import { tokens } from '@/design';
import type { CardsSort, CardSummary, Rarity, SlimeType } from '@/api/types';
import { CARDS, CARDS_BY_SERIAL, SUMMARIES, TODAY_SERIAL, buildRaw } from './data';
import { mockCardSvg } from './sprite';

/** A little latency so loading states are exercised, not so much it drags. */
const LATENCY = 120;

const GENESIS_TOTAL = 365_000;
const BLOOM_FEE = 100;
const TOTAL_BLOOMS = 3_650;

function notFound(message: string) {
  return HttpResponse.json({ error: { code: 'not_found', message } }, { status: 404 });
}

function parseSerial(raw: string | readonly string[] | undefined): number | null {
  const value = Number(Array.isArray(raw) ? raw[0] : raw);
  if (!Number.isInteger(value) || value < 1 || value > 65_535) return null;
  return value;
}

/* ─────────────────────────── time ─────────────────────────── */

/** Milliseconds to add to a UTC instant to get the Europe/Paris wall clock. */
function parisOffsetMs(at: Date): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris', hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
  const parts: Record<string, number> = {};
  for (const p of dtf.formatToParts(at)) if (p.type !== 'literal') parts[p.type] = Number(p.value);
  const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
  return asUtc - at.getTime();
}

/** The UTC instant at which the Paris wall clock next reads 10:00:00. */
function nextBloomAt(now: Date): Date {
  const parisNow = new Date(now.getTime() + parisOffsetMs(now));
  const y = parisNow.getUTCFullYear();
  const m = parisNow.getUTCMonth();
  const d = parisNow.getUTCDate();
  const toUtc = (day: number): Date => {
    const guess = new Date(Date.UTC(y, m, day, 10, 0, 0));
    return new Date(guess.getTime() - parisOffsetMs(guess));
  };
  const today = toUtc(d);
  return today.getTime() > now.getTime() ? today : toUtc(d + 1);
}

/* ─────────────────────────── stats ─────────────────────────── */

function countBy<K extends string>(pick: (serial: number) => K): Record<K, number> {
  const out = {} as Record<K, number>;
  for (const card of CARDS) {
    const key = pick(card.serial);
    out[key] = (out[key] ?? 0) + 1;
  }
  return out;
}

function collectionStats() {
  const byRarity = countBy<Rarity>((s) => CARDS_BY_SERIAL.get(s)!.rarity);
  const byType = countBy<SlimeType>((s) => CARDS_BY_SERIAL.get(s)!.type);
  const total = CARDS.length;
  return {
    total,
    byRarity,
    byType,
    genesisRemaining: GENESIS_TOTAL - total * BLOOM_FEE,
    bloomsRemaining: TOTAL_BLOOMS - total,
  };
}

/* ─────────────────────────── query ─────────────────────────── */

const RARITY_RANK: Record<Rarity, number> = {
  MYTHIC: 0, LEGENDARY: 1, EPIC: 2, RARE: 3, UNCOMMON: 4, COMMON: 5,
};

/** Contract: every sort is tie-broken by `serial` descending, keeping pagination stable. */
const bySerialDesc = (a: CardSummary, b: CardSummary): number => b.serial - a.serial;

function sortSummaries(items: readonly CardSummary[], sort: CardsSort): CardSummary[] {
  const copy = [...items];
  switch (sort) {
    case 'oldest':
      return copy.sort((a, b) => a.mintDate.localeCompare(b.mintDate) || bySerialDesc(a, b));
    case 'rarest':
      return copy.sort((a, b) => RARITY_RANK[a.rarity] - RARITY_RANK[b.rarity] || bySerialDesc(a, b));
    case 'happiest':
      return copy.sort(
        (a, b) =>
          (CARDS_BY_SERIAL.get(b.serial)?.happiness ?? 0) -
            (CARDS_BY_SERIAL.get(a.serial)?.happiness ?? 0) || bySerialDesc(a, b),
      );
    case 'newest':
    default:
      return copy.sort((a, b) => b.mintDate.localeCompare(a.mintDate) || bySerialDesc(a, b));
  }
}

/* ─────────────────────────── handlers ─────────────────────────── */

export const handlers = [
  http.get('/api/health', async () => {
    await delay(LATENCY);
    return HttpResponse.json({ status: 'ok', cards: CARDS.length, engine: 'asmdb-mock/1.0' });
  }),

  http.get('/api/cards/today', async () => {
    await delay(LATENCY);
    const card = CARDS_BY_SERIAL.get(TODAY_SERIAL);
    if (!card) return notFound('No card has bloomed today yet');
    const now = new Date();
    const next = nextBloomAt(now);
    return HttpResponse.json({
      card,
      nextBloomAt: next.toISOString(),
      secondsUntilNext: Math.max(0, Math.floor((next.getTime() - now.getTime()) / 1000)),
      dayNumber: card.dayNumber ?? TODAY_SERIAL,
    });
  }),

  http.get('/api/cards', async ({ request }) => {
    await delay(LATENCY);
    const url = new URL(request.url);
    const page = Math.max(1, Number(url.searchParams.get('page') ?? 1) || 1);
    const size = Math.min(100, Math.max(1, Number(url.searchParams.get('size') ?? 24) || 24));
    const type = url.searchParams.get('type') as SlimeType | null;
    const rarity = url.searchParams.get('rarity') as Rarity | null;
    const sort = (url.searchParams.get('sort') ?? 'newest') as CardsSort;
    const q = (url.searchParams.get('q') ?? '').trim().toLowerCase();

    let items = SUMMARIES.filter((c) => {
      if (type && c.type !== type) return false;
      if (rarity && c.rarity !== rarity) return false;
      if (q && !c.name.toLowerCase().includes(q)) return false;
      return true;
    });
    items = sortSummaries(items, sort);

    const total = items.length;
    const start = (page - 1) * size;
    const paged = items.slice(start, start + size);
    return HttpResponse.json({
      items: paged,
      page,
      size,
      total,
      hasMore: start + size < total,
    });
  }),

  http.get('/api/cards/:serial/raw', async ({ params }) => {
    await delay(LATENCY);
    const serial = parseSerial(params.serial);
    const card = serial ? CARDS_BY_SERIAL.get(serial) : undefined;
    if (!card) return notFound('No such card');
    return HttpResponse.json(buildRaw(card));
  }),

  http.get('/api/cards/:serial/image', ({ params }) => {
    const serial = parseSerial(params.serial);
    const card = serial ? CARDS_BY_SERIAL.get(serial) : undefined;
    if (!card) return notFound('No such card');
    if (card.imageUrl.startsWith('/mock/')) {
      return HttpResponse.redirect(card.imageUrl, 302);
    }
    return svgResponse(serial!);
  }),

  http.get('/api/cards/:serial/thumb', ({ params }) => {
    const serial = parseSerial(params.serial);
    const card = serial ? CARDS_BY_SERIAL.get(serial) : undefined;
    if (!card) return notFound('No such card');
    if (card.thumbUrl.startsWith('/mock/')) {
      return HttpResponse.redirect(card.thumbUrl, 302);
    }
    return svgResponse(serial!);
  }),

  http.get('/api/cards/:serial', async ({ params }) => {
    await delay(LATENCY);
    const serial = parseSerial(params.serial);
    const card = serial ? CARDS_BY_SERIAL.get(serial) : undefined;
    if (!card) return notFound('No such card');
    return HttpResponse.json(card);
  }),

  http.get('/api/stats', async () => {
    await delay(LATENCY);
    return HttpResponse.json(collectionStats());
  }),

  http.get('/api/nft/:serial', async ({ params }) => {
    await delay(LATENCY);
    const serial = parseSerial(params.serial);
    const card = serial ? CARDS_BY_SERIAL.get(serial) : undefined;
    if (!card) return notFound('No such card');
    return HttpResponse.json({
      name: `${card.name} · ${card.cardId}`,
      description: `${card.personality} — a ${card.rarity} ${card.type} PixelSlime.`,
      image: card.imageUrl,
      external_url: `https://pixelslime.example/slime/${card.serial}`,
      attributes: [
        { trait_type: 'Rarity', value: card.rarity },
        { trait_type: 'House', value: card.rarityHouse },
        { trait_type: 'Type', value: card.type },
        { trait_type: 'Mood', value: card.mood ?? 'Unknown' },
        { trait_type: 'Level', value: card.level, display_type: 'number' },
        { trait_type: 'Strength', value: card.strength, display_type: 'number' },
        { trait_type: 'Endurance', value: card.endurance, display_type: 'number' },
        { trait_type: 'Agility', value: card.agility, display_type: 'number' },
        { trait_type: 'Happiness', value: card.happiness, display_type: 'number' },
        { trait_type: 'Day', value: card.dayNumber ?? card.serial, display_type: 'number' },
      ],
    });
  }),

  http.post('/api/admin/generate', async ({ request }) => {
    await delay(LATENCY);
    if (!request.headers.get('X-PixelSlime-Admin')) {
      return HttpResponse.json({ error: { code: 'unauthorized', message: 'Missing admin token' } }, { status: 401 });
    }
    let dryRun = false;
    try {
      const body = (await request.json()) as { dryRun?: boolean } | null;
      dryRun = body?.dryRun ?? false;
    } catch {
      dryRun = false;
    }
    if (dryRun) return new HttpResponse(null, { status: 202 });
    return HttpResponse.json(
      { error: { code: 'already_bloomed', message: 'A card already exists for today' } },
      { status: 409 },
    );
  }),
];

function svgResponse(serial: number) {
  const card = CARDS_BY_SERIAL.get(serial)!;
  const svg = mockCardSvg({
    baseColor: card.palette?.[0] ?? tokens.color.mint,
    accessory: 'none',
    face: 'happy',
    rarityColor: tokens.rarity[card.rarity].color,
  });
  return new HttpResponse(svg, { headers: { 'Content-Type': 'image/svg+xml; charset=utf-8' } });
}
