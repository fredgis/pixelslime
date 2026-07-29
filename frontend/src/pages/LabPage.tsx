/**
 * ④ PUNI LAB (`/lab`).
 *
 * Explains the lore, the six rarity houses with their real odds/yields/adoption prices
 * (all from the design tokens — never invented), the sixteen types, and how a card is
 * born (the daily pipeline that ends as 175 bytes anchored on-chain). Little slimes
 * demonstrate throughout.
 */
import type { ReactElement } from 'react';
import {
  Chip,
  RARITY_ORDER,
  RarityBadge,
  SLIME_TYPES,
  SlimeSprite,
  TypePill,
  tokens,
} from '@/design';
import { HeroTitle } from '@/components/HeroTitle';

const TOTAL_BLOOMS = 3_650;

const BIRTH_STEPS: ReadonlyArray<{ title: string; body: string; color: string }> = [
  { title: 'SEED', body: 'A daily seed rolls the slime: rarity, type, stats, biome and a companion.', color: tokens.color.bubblegum },
  { title: 'PAINT', body: 'A pixel-art portrait is generated and vision-checked until it matches the card.', color: tokens.color.sky },
  { title: 'PACK', body: 'Every field is packed into a PSC-1 stream and Z85-encoded — about 175 bytes.', color: tokens.color.mint },
  { title: 'ANCHOR', body: 'keccak-256 hashes the stream; that hash is minted on Polygon Amoy.', color: tokens.color.sunbeam },
  { title: 'BLOOM', body: 'At 10:00 Paris the card blooms into the SLIMEDEX for everyone to meet.', color: tokens.color.grape },
];

function oddsLabel(weight: number): string {
  return `${Number((weight * 100).toFixed(2))}%`;
}

export function LabPage(): ReactElement {
  return (
    <div className="flex flex-col gap-12">
      <section className="ps-hero">
        <HeroTitle text="PUNI LAB" eyebrow="FIELD NOTES" subtitle="HOW A SLIME IS BORN" />
        <p className="mx-auto mt-6 max-w-2xl font-round text-ink">
          Every day, one slime blooms in the PUNIPUNI PARADISE. Each is a tiny, self-contained
          creature — a rarity, a mood, four stats and a story — squished down to a handful of bytes
          and anchored on-chain so it can never be quietly changed. Here’s how the magic works.
        </p>
      </section>

      <section aria-labelledby="houses-heading">
        <h2 id="houses-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          THE SIX HOUSES OF RARITY
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {RARITY_ORDER.map((r) => {
            const info = tokens.rarity[r];
            const census = Math.round(info.weight * TOTAL_BLOOMS);
            return (
              <div key={r} className="flex flex-col gap-3 rounded-lg border-4 border-ink bg-paper p-4 shadow-card">
                <div className="flex items-center justify-between gap-2">
                  <RarityBadge rarity={r} format="full" />
                  <SlimeSprite baseColor={info.color} face="happy" size={44} bob />
                </div>
                <dl className="grid grid-cols-2 gap-2 font-stat text-[12px] text-ink-soft">
                  <Stat label="ODDS" value={oddsLabel(info.weight)} />
                  <Stat label="YIELD" value={`×${info.yieldMultiplier}`} />
                  <Stat label="ADOPT" value={`${info.adoptPrice.toLocaleString()} $SMILE`} />
                  <Stat label="OF 3,650" value={`≈${census.toLocaleString()}`} />
                </dl>
              </div>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="types-heading">
        <h2 id="types-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          SIXTEEN MOODS
        </h2>
        <ul className="flex flex-wrap justify-center gap-3">
          {SLIME_TYPES.map((t) => (
            <li key={t}>
              <TypePill type={t} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="birth-heading">
        <h2 id="birth-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          HOW A CARD IS BORN
        </h2>
        <ol className="grid gap-4 md:grid-cols-5">
          {BIRTH_STEPS.map((step, i) => (
            <li key={step.title} className="flex flex-col items-center gap-3 rounded-lg border-4 border-ink bg-paper p-4 text-center shadow-card">
              <span className="font-pixel text-[12px]" style={{ color: step.color }}>
                {i + 1}
              </span>
              <SlimeSprite baseColor={step.color} accessory={i % 2 ? 'star' : 'leaf'} face="happy" size={52} bob />
              <h3 className="font-pixel text-[11px] text-ink">{step.title}</h3>
              <p className="font-round text-[14px] text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-xl border-4 border-ink bg-paper p-6 text-center shadow-card">
        <div className="mb-3 flex justify-center gap-2">
          <Chip tone={tokens.color.mint} icon="✦">175 bytes</Chip>
          <Chip tone={tokens.color.sky} icon="⛓">on-chain forever</Chip>
          <Chip tone={tokens.color.bubblegum} icon="☀">one a day</Chip>
        </div>
        <p className="mx-auto max-w-xl font-round text-ink">
          3,650 slimes will bloom over exactly ten years — then the rain stops, and the paradise is
          complete. Every one is a treasure you can hold in 175 bytes.
        </p>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }): ReactElement {
  return (
    <div className="rounded-md border-4 border-ink bg-cream px-2 py-1">
      <dt className="text-[10px] tracking-[1px] text-ink-soft">{label}</dt>
      <dd className="font-round text-[14px] text-ink">{value}</dd>
    </div>
  );
}

export default LabPage;
