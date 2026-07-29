/**
 * ⑤ SMILE BANK (`/bank`).
 *
 * The Genesis Rain countdown (365,000 SMILE, 100 burned per bloom → 3,650 slimes = exactly
 * ten years), the burn → mint → claim flow, adoption prices per tier, and the on-chain
 * anchors list. Every figure is the settled number from docs/PLAN.md §8.3/§8.6 or the design
 * tokens — nothing here is invented; the live "remaining" comes from `/api/stats`.
 */
import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';
import {
  AnimatedTitle,
  Chip,
  RARITY_ORDER,
  RarityBadge,
  SlimeSprite,
  tokens,
} from '@/design';
import { useCards, useStats } from '@/api/client';
import { formatMintDate } from '@/lib/cards';
import { LoadingState } from '@/components/States';

const GENESIS_TOTAL = 365_000;
const TOTAL_BLOOMS = 3_650;

const FLOW: ReadonlyArray<{ icon: string; title: string; body: string; color: string }> = [
  { icon: '🌧️', title: 'GENESIS RAIN', body: '365,000 $SMILE minted once at deployment. Finite — the minter role is renounced, so it can never be refilled.', color: tokens.color.sunbeam },
  { icon: '🔥', title: 'BLOOM BURN', body: 'Every bloom the Treasury pays a 100 $SMILE fee — and it is burned forever. The puddle only ever shrinks.', color: tokens.color.coral },
  { icon: '💧', title: 'CLAIM POOL', body: 'Each slime mints ~248 $SMILE of fresh happiness into a pool the Treasury cannot touch.', color: tokens.color.sky },
  { icon: '🧑‍🌾', title: 'ADOPT', body: 'Keepers claim $SMILE with an EIP-712 voucher, then spend it to adopt a slime out of the Vault.', color: tokens.color.mint },
];

export function BankPage(): ReactElement {
  const stats = useStats();
  const recent = useCards({ sort: 'newest', size: 8 });

  const genesisRemaining = stats.data?.genesisRemaining ?? GENESIS_TOTAL;
  const bloomsRemaining = stats.data?.bloomsRemaining ?? TOTAL_BLOOMS;
  const bloomed = TOTAL_BLOOMS - bloomsRemaining;
  const depletedPct = Math.min(100, Math.max(0, ((GENESIS_TOTAL - genesisRemaining) / GENESIS_TOTAL) * 100));

  return (
    <div className="flex flex-col gap-12">
      <section className="ps-hero">
        <AnimatedTitle text="SMILE BANK" eyebrow="THE $SMILE ECONOMY" subtitle="THE GENESIS RAIN" />
      </section>

      <section
        aria-labelledby="genesis-heading"
        className="rounded-xl border-4 border-ink p-6 shadow-card"
        style={{ background: tokens.color.ink }}
      >
        <h2 id="genesis-heading" className="font-pixel text-[13px]" style={{ color: tokens.color.sunbeam }}>
          GENESIS RAIN REMAINING
        </h2>
        {stats.isLoading ? (
          <p className="mt-3 font-stat text-[14px]" style={{ color: tokens.color.mint }}>
            Counting $SMILE…
          </p>
        ) : (
          <>
            <p className="mt-2 font-pixel text-[26px] leading-tight" style={{ color: tokens.color.cream }}>
              {genesisRemaining.toLocaleString()} <span style={{ color: tokens.color.mint }}>$SMILE</span>
            </p>
            <p className="mt-1 font-stat text-[13px] tracking-[1px]" style={{ color: tokens.color.sky }}>
              {bloomsRemaining.toLocaleString()} slimes left · {bloomed.toLocaleString()} bloomed so far
            </p>
            <div
              className="mt-4 h-4 w-full overflow-hidden rounded-pill border-4"
              style={{ borderColor: tokens.color.grape }}
              role="progressbar"
              aria-valuenow={Math.round(depletedPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Genesis Rain depleted"
            >
              <div className="h-full" style={{ width: `${depletedPct}%`, background: tokens.color.coral }} />
            </div>
            <p className="mt-4 font-stat text-[12px]" style={{ color: tokens.color.cream }}>
              365,000 ÷ 100 per bloom = <b style={{ color: tokens.color.sunbeam }}>3,650 blooms</b> = exactly 10 years
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="flow-heading">
        <h2 id="flow-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          BURN · MINT · CLAIM
        </h2>
        <ol className="grid gap-4 md:grid-cols-4">
          {FLOW.map((step) => (
            <li key={step.title} className="flex flex-col gap-2 rounded-lg border-4 border-ink bg-paper p-4 shadow-card">
              <span className="text-2xl" aria-hidden>
                {step.icon}
              </span>
              <h3 className="font-pixel text-[11px]" style={{ color: step.color }}>
                {step.title}
              </h3>
              <p className="font-round text-[14px] text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
        <p className="mx-auto mt-4 max-w-2xl text-center font-round text-ink-soft">
          The left branch only drains a finite purse; the right branch only fills a pool that purse cannot
          reach. The lore and the ledger agree exactly.
        </p>
      </section>

      <section aria-labelledby="adopt-heading">
        <h2 id="adopt-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          ADOPTION PRICES
        </h2>
        <div className="overflow-hidden rounded-lg border-4 border-ink shadow-card">
          <table className="w-full border-collapse bg-paper text-left">
            <caption className="sr-only">Adoption price and bloom yield multiplier per rarity tier</caption>
            <thead>
              <tr className="border-b-4 border-ink font-stat text-[11px] tracking-[1px] text-ink-soft">
                <th scope="col" className="px-4 py-2">TIER</th>
                <th scope="col" className="px-4 py-2 text-right">ADOPT ($SMILE)</th>
                <th scope="col" className="px-4 py-2 text-right">YIELD</th>
              </tr>
            </thead>
            <tbody>
              {RARITY_ORDER.map((r) => {
                const info = tokens.rarity[r];
                return (
                  <tr key={r} className="border-b-4 border-ink last:border-b-0">
                    <td className="px-4 py-2">
                      <RarityBadge rarity={r} format="full" size="sm" />
                    </td>
                    <td className="px-4 py-2 text-right font-round text-ink">{info.adoptPrice.toLocaleString()}</td>
                    <td className="px-4 py-2 text-right font-round text-ink">×{info.yieldMultiplier}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mx-auto mt-3 max-w-2xl text-center font-stat text-[12px] tracking-[1px] text-ink-soft">
          Expected yield ≈ 75 happiness × 3.31 average multiplier ≈ 248 $SMILE/day, against a 100 $SMILE burn.
        </p>
      </section>

      <section aria-labelledby="anchors-heading">
        <h2 id="anchors-heading" className="mb-5 text-center font-pixel text-[16px] text-ink">
          ON-CHAIN ANCHORS
        </h2>
        {recent.isLoading ? (
          <LoadingState label="Reading the ledger…" />
        ) : (
          <ul className="flex flex-col gap-2">
            <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-4 border-dashed border-ink bg-cream px-4 py-3">
              <span className="font-stat text-[12px] tracking-[1px] text-ink-soft">NEXT BLOOM</span>
              <span className="font-round text-ink-soft">pending · 10:00 Paris</span>
              <Chip tone={tokens.color.sky}>ANCHOR SOON</Chip>
            </li>
            {(recent.data?.items ?? []).map((item) => (
              <li
                key={item.serial}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-4 border-ink bg-paper px-4 py-3 shadow-card"
              >
                <span className="font-stat text-[12px] tracking-[1px] text-ink">{item.cardId}</span>
                <span className="font-round text-ink">{item.name}</span>
                <span className="font-stat text-[11px] tracking-[1px] text-ink-soft">
                  {formatMintDate(item.mintDate)}
                </span>
                <Link to={`/slime/${item.serial}`} className="ps-focusable">
                  <Chip tone={item.onChain ? tokens.color.mint : tokens.color.sky} icon={item.onChain ? '⛓' : '…'}>
                    {item.onChain ? 'ON-CHAIN' : 'PENDING'}
                  </Chip>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border-4 border-ink bg-paper p-6 shadow-card">
        <div className="mb-4 flex flex-wrap justify-center gap-2">
          <Chip tone={tokens.color.sunbeam}>Amoy testnet</Chip>
          <Chip tone={tokens.color.coral}>Genesis 0 at the end</Chip>
          <Chip tone={tokens.color.mint}>≈905,000 $SMILE earned</Chip>
          <Chip tone={tokens.color.sky}>gas €0 · faucet MATIC</Chip>
        </div>
        <div className="flex items-center justify-center gap-3">
          <SlimeSprite baseColor={tokens.color.sunbeam} accessory="star" face="happy" size={56} bob />
          <p className="max-w-xl font-round text-ink">
            At the end, the Genesis Rain is completely gone — burned one slime at a time — and everything
            still standing was earned by a slime radiating happiness.
          </p>
        </div>
      </section>
    </div>
  );
}

export default BankPage;
