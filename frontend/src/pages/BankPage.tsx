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

/**
 * The two halves of a bloom, side by side and moving in opposite directions.
 *
 * This is the clearest way to show the rule the whole economy rests on: the purse
 * that pays the fee is not the purse that earns the yield. Putting the draining
 * reserve next to the filling pool makes that visible at a glance — and makes it
 * obvious that the left number can never be replenished by the right one.
 */
function TwinCounters({
  burned,
  pool,
  loading,
}: {
  burned: number;
  pool: number;
  loading: boolean;
}): ReactElement {
  return (
    <section aria-labelledby="twin-heading" className="flex flex-col gap-4">
      <h2
        id="twin-heading"
        className="text-center font-pixel text-[16px] text-ink"
      >
        EVERY BLOOM, TWO OPPOSITE MOVES
      </h2>

      <div className="grid gap-5 md:grid-cols-2">
        <div
          className="rounded-xl border-4 border-ink p-5 shadow-card"
          style={{ background: tokens.color.coral }}
        >
          <p className="font-pixel text-[11px]" style={{ color: tokens.color.cream }}>
            🔥 BURNED FROM THE RESERVE
          </p>
          <p
            className="mt-2 font-pixel text-[24px] leading-tight"
            style={{ color: tokens.color.cream }}
            aria-live="polite"
          >
            {loading ? '…' : `−${burned.toLocaleString()}`}{' '}
            <span className="text-[14px]">$SMILE</span>
          </p>
          <p className="mt-2 font-stat text-[12px]" style={{ color: tokens.color.cream }}>
            100 per bloom, destroyed forever. This number only ever goes up, and the
            reserve behind it only ever goes down.
          </p>
        </div>

        <div
          className="rounded-xl border-4 border-ink p-5 shadow-card"
          style={{ background: tokens.color.sky }}
        >
          <p className="font-pixel text-[11px]" style={{ color: tokens.color.ink }}>
            ✨ MINTED INTO THE CLAIM POOL
          </p>
          <p
            className="mt-2 font-pixel text-[24px] leading-tight"
            style={{ color: tokens.color.ink }}
            aria-live="polite"
          >
            {loading ? '…' : `+${pool.toLocaleString()}`}{' '}
            <span className="text-[14px]">$SMILE</span>
          </p>
          <p className="mt-2 font-stat text-[12px]" style={{ color: tokens.color.ink }}>
            happiness × rarity, created fresh for each slime — into a purse the
            reserve cannot reach.
          </p>
        </div>
      </div>

      <p
        className="text-center font-stat text-[12px] text-ink-soft"
        style={{ lineHeight: 1.7 }}
      >
        The one who <b>pays</b> and the one who <b>earns</b> are never the same purse.
        That is what makes the fee real: if the reserve could mint, it would simply
        refill itself.
      </p>
    </section>
  );
}

/** Live contracts on Polygon Amoy. Kept here so the numbers above can be audited. */
const CONTRACTS: ReadonlyArray<{
  label: string;
  symbol?: string;
  kind: string;
  address: string;
  path: 'token' | 'address';
  note: string;
}> = [
  {
    label: 'PixelSlime Card',
    symbol: 'SLIME',
    kind: 'ERC-721 · the cards',
    address: '0xD88928B55CefcAe756e55824a48342cA432Baf7f',
    path: 'token',
    note: 'One token per slime, indivisible. Only ever grows.',
  },
  {
    label: 'PixelSlime Smile',
    symbol: 'SMILE',
    kind: 'ERC-20 · the money',
    address: '0x0BBaC39Bf418ab63BF71802808A4C63D4B39b798',
    path: 'token',
    note: 'Burned 100 per bloom, minted as yield. 18 decimals.',
  },
  {
    label: 'Claim Pool',
    kind: 'holds the yield',
    address: '0xbce1362c1155777df19F9cea6c8ECa68B155160d',
    path: 'address',
    note: 'The only address allowed to mint $SMILE.',
  },
  {
    label: 'Treasury (Vault)',
    kind: 'the Genesis Rain',
    address: '0xb71C9B63ba13d2a34DD895A4De577661A963FaAc',
    path: 'address',
    note: 'Holds every card and the shrinking reserve. Cannot mint.',
  },
];

/**
 * Where to go and check any of this for yourself.
 *
 * Every figure on this page is a claim about a public ledger, and a claim nobody can
 * verify is just a nicer-looking number. SLIME and SMILE are listed side by side
 * because they are one letter apart and easy to confuse — one is the card, the other
 * is the currency.
 */
function ContractDirectory(): ReactElement {
  return (
    <section aria-labelledby="contracts-heading">
      <h2 id="contracts-heading" className="mb-2 text-center font-pixel text-[16px] text-ink">
        VERIFY IT YOURSELF
      </h2>
      <p className="mb-5 text-center font-stat text-[12px] text-ink-soft">
        Every number above is on a public chain. Polygon Amoy testnet.
      </p>

      <ul className="grid gap-3 md:grid-cols-2">
        {CONTRACTS.map((c) => (
          <li
            key={c.address}
            className="rounded-lg border-4 border-ink bg-cream p-4 shadow-card"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-pixel text-[12px] text-ink">{c.label}</span>
              {c.symbol ? <Chip tone={tokens.color.sunbeam}>{c.symbol}</Chip> : null}
            </div>
            <p className="mt-1 font-stat text-[11px] tracking-[1px] text-ink-soft">{c.kind}</p>
            <a
              href={`https://amoy.polygonscan.com/${c.path}/${c.address}`}
              target="_blank"
              rel="noreferrer"
              className="ps-focusable mt-2 block break-all font-stat text-[11px] underline"
              style={{ color: tokens.color.grape }}
            >
              {c.address}
            </a>
            <p className="mt-2 font-round text-[13px] text-ink-soft" style={{ lineHeight: 1.5 }}>
              {c.note}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function BankPage(): ReactElement {
  const stats = useStats();
  const recent = useCards({ sort: 'newest', size: 8 });

  const genesisRemaining = stats.data?.genesisRemaining ?? GENESIS_TOTAL;
  const bloomsRemaining = stats.data?.bloomsRemaining ?? TOTAL_BLOOMS;
  const genesisBurned = stats.data?.genesisBurned ?? 0;
  const poolTotal = stats.data?.poolTotal ?? 0;
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

      <TwinCounters
        burned={genesisBurned}
        pool={poolTotal}
        loading={stats.isLoading}
      />

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

      <ContractDirectory />

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
