/**
 * ③ SLIME PROFILE (`/slime/:serial`).
 *
 * The card at full size with the pointer/gyroscope holo tilt, a cascade of stat bars,
 * the full lore (biome, companion, birth date, serial), the on-chain badge when present,
 * and the "see the 175 bytes" provenance panel driven by `/api/cards/{serial}/raw` — the
 * genuine Z85 rows, their count, the stream length and the keccak-256 cardHash. Opening a
 * profile discovers the card (localStorage) and tints the page to its palette.
 */
import { useEffect, useState, type ReactElement } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Chip,
  HoloCard,
  RarityBadge,
  StatBar,
  TypePill,
  tokens,
  type StatKey,
} from '@/design';
import { useCard, useRawCard } from '@/api/client';
import { formatMintDate, paletteBackground } from '@/lib/cards';
import { useAmbientStore } from '@/store/ambient';
import { useDiscoveryStore } from '@/store/discovery';
import { SmartImage } from '@/components/SmartImage';
import { ErrorState, LoadingState } from '@/components/States';
import { toast } from '@/store/toast';

export function ProfilePage(): ReactElement {
  const { serial: serialParam } = useParams();
  const serial = Number(serialParam);
  const valid = Number.isInteger(serial) && serial > 0;
  const card = useCard(valid ? serial : undefined);
  const setTint = useAmbientStore((s) => s.setTint);
  const discover = useDiscoveryStore((s) => s.discover);
  const [showBytes, setShowBytes] = useState(false);

  const data = card.data;

  useEffect(() => {
    if (data) {
      discover(data.serial);
      setTint(paletteBackground(data));
    }
    return () => setTint(null);
  }, [data, discover, setTint]);

  if (!valid) return <ErrorState label="That serial doesn’t look right." />;
  if (card.isLoading) return <LoadingState label="Fetching the slime…" />;
  if (card.isError || !data) {
    return <ErrorState label="No slime with that serial." onRetry={() => void card.refetch()} />;
  }

  const stats: ReadonlyArray<[StatKey, number]> = [
    ['strength', data.strength],
    ['endurance', data.endurance],
    ['agility', data.agility],
    ['happiness', data.happiness],
  ];

  return (
    <article className="flex flex-col gap-6">
      <Link to="/dex" className="ps-focusable self-start font-stat text-[12px] tracking-[2px] text-ink-soft">
        ← BACK TO SLIMEDEX
      </Link>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,360px)_1fr]">
        <div className="mx-auto w-full max-w-[360px]">
          <HoloCard imageAlt={`${data.name}, a ${data.rarity} ${data.type} slime`}>
            <SmartImage
              src={data.imageUrl}
              thumb={data.thumbUrl}
              alt={`${data.name}, a ${data.rarity} ${data.type} slime`}
              sizes="(max-width: 640px) 90vw, 360px"
              eager
            />
          </HoloCard>
        </div>

        <div className="flex flex-col gap-5">
          <header className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h1 className="font-pixel text-[24px] text-ink">{data.name}</h1>
              {data.onChain && data.chain ? (
                <a
                  href={data.chain.explorerUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="ps-focusable"
                  aria-label={`View ${data.name} on-chain, token ${data.chain.tokenId}`}
                >
                  <Chip tone={tokens.color.mint} icon="⛓">
                    ON-CHAIN #{data.chain.tokenId}
                  </Chip>
                </a>
              ) : (
                <Chip tone={tokens.color.sky}>ANCHOR PENDING</Chip>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <RarityBadge rarity={data.rarity} />
              <TypePill type={data.type} />
              <Chip>LV {data.level}</Chip>
              {data.shiny ? <Chip tone={tokens.color.sunbeam} icon="✨">SHINY</Chip> : null}
            </div>
            <p className="font-stat text-[12px] tracking-[2px] text-ink-soft">
              {data.cardId} · {formatMintDate(data.mintDate)}
              {data.dayNumber ? ` · DAY ${data.dayNumber}` : ''}
            </p>
          </header>

          <div className="grid gap-2 sm:grid-cols-2">
            {stats.map(([stat, value], i) => (
              <StatBar key={stat} stat={stat} value={value} index={i} />
            ))}
          </div>

          <section className="rounded-lg border-4 border-ink bg-paper p-5 shadow-card">
            <p className="font-round text-ink">{data.personality}</p>
            <div className="mt-3 rounded-md border-4 border-ink bg-cream p-3">
              <p className="font-pixel text-[11px] text-ink">✦ {data.power_name}</p>
              <p className="mt-1 font-round text-ink-soft">{data.power_desc}</p>
            </div>
            <p className="mt-3 font-stat text-[13px] italic text-ink-soft">“{data.quote}”</p>
          </section>

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Fact label="BIOME" value={data.biome ?? '—'} />
            <Fact label="MOOD" value={data.mood ?? '—'} />
            <Fact label="COMPANION" value={data.companion ?? '—'} />
            <Fact label="HOUSE" value={data.rarityHouse ?? tokens.rarity[data.rarity].house} />
            <Fact label="HEIGHT" value={`${data.height_mm} mm`} />
            <Fact label="WEIGHT" value={`${data.weight_g} g`} />
            <Fact label="SERIAL" value={data.cardId} />
          </dl>
        </div>
      </div>

      <ProvenancePanel serial={data.serial} open={showBytes} onToggle={() => setShowBytes((v) => !v)} />
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }): ReactElement {
  return (
    <div className="rounded-md border-4 border-ink bg-paper p-3">
      <dt className="font-stat text-[10px] tracking-[2px] text-ink-soft">{label}</dt>
      <dd className="mt-1 font-round text-ink">{value}</dd>
    </div>
  );
}

interface ProvenancePanelProps {
  serial: number;
  open: boolean;
  onToggle: () => void;
}

function ProvenancePanel({ serial, open, onToggle }: ProvenancePanelProps): ReactElement {
  const raw = useRawCard(open ? serial : undefined);

  const copyHash = (hash: string): void => {
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(hash).then(() => toast('Card hash copied', '📋'));
    }
  };

  return (
    <section
      aria-labelledby="provenance-heading"
      className="rounded-xl border-4 border-ink p-5 shadow-card"
      style={{ background: tokens.color.ink }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="provenance-heading" className="font-pixel text-[14px]" style={{ color: tokens.color.sunbeam }}>
            ✦ THE 175 BYTES
          </h2>
          <p className="mt-1 font-stat text-[11px] tracking-[1px]" style={{ color: tokens.color.mint }}>
            The exact PSC-1 payload this card lives as, in asmDB.
          </p>
        </div>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="ps-focusable rounded-pill border-4 px-4 py-1.5 font-pixel text-[11px]"
          style={{ borderColor: tokens.color.mint, color: tokens.color.cream, background: 'transparent' }}
        >
          {open ? 'RESEAL' : 'UNSEAL ▸'}
        </button>
      </div>

      {open ? (
        raw.isLoading ? (
          <p className="mt-4 font-stat text-[12px]" style={{ color: tokens.color.mint }}>
            Decoding the stream…
          </p>
        ) : raw.isError || !raw.data ? (
          <p className="mt-4 font-stat text-[12px]" style={{ color: tokens.color.coral }}>
            Could not read the provenance stream.
          </p>
        ) : (
          <div className="mt-4 flex flex-col gap-4">
            <div className="flex flex-wrap gap-4 font-stat text-[12px]" style={{ color: tokens.color.cream }}>
              <span>
                <b style={{ color: tokens.color.sunbeam }}>{raw.data.streamBytes}</b> bytes
              </span>
              <span>
                <b style={{ color: tokens.color.sunbeam }}>{raw.data.rowCount}</b> asmDB rows
              </span>
              <span>Z85 · keccak-256 anchored</span>
            </div>

            <button
              type="button"
              onClick={() => copyHash(raw.data!.cardHash)}
              className="ps-focusable overflow-x-auto rounded-md border-4 p-3 text-left font-stat text-[12px]"
              style={{ borderColor: tokens.color.grape, color: tokens.color.mint, background: 'transparent' }}
              aria-label="Copy card hash"
              title="Copy card hash"
            >
              <span style={{ color: tokens.color.sky }}>cardHash</span> = {raw.data.cardHash}
            </button>

            <ol className="flex flex-col gap-2">
              {raw.data.rows.map((row) => (
                <li
                  key={row.id}
                  className="rounded-md border-4 p-3 font-stat text-[11px] leading-relaxed"
                  style={{ borderColor: tokens.color.grape, color: tokens.color.mint }}
                >
                  <div className="mb-1 flex flex-wrap gap-3" style={{ color: tokens.color.sky }}>
                    <span>{row.tag}</span>
                    <span>id:{row.id}</span>
                    <span>val:{row.value}</span>
                    <span>{row.content.length} chars</span>
                  </div>
                  <code className="block break-all" style={{ color: tokens.color.cream }}>
                    {row.content}
                  </code>
                </li>
              ))}
            </ol>
          </div>
        )
      ) : (
        <p className="mt-4 font-stat text-[12px]" style={{ color: tokens.color.mint }}>
          175 bytes, encoded in Z85, anchored on-chain by keccak-256. Unseal to inspect the real rows.
        </p>
      )}
    </section>
  );
}

export default ProfilePage;
