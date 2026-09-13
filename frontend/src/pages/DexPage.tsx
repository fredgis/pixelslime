/**
 * ② SLIMEDEX (`/dex`).
 *
 * The gallery: a grid of tiles (entrance-staggered, hover-tilt + rarity-scaled holo via
 * the design's SlimeCard), with rarity/type filters, a debounced name search and sort.
 * Cards this visitor has not opened render as dark "???" silhouettes — a Pokédex
 * discovery mechanic tracked purely in localStorage (nothing about a visitor is ever
 * sent to the server). Opening a card's profile discovers it.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PixelButton,
  RARITY_ORDER,
  SLIME_TYPES,
  SlimeCard,
  tokens,
  useReducedMotion,
  type Rarity,
  type SlimeType,
} from '@/design';
import { useCards } from '@/api/client';
import type { CardsSort } from '@/api/types';
import { toSlimeCardData } from '@/lib/cards';
import { useDiscoveryStore } from '@/store/discovery';
import { EmptyState, ErrorState, LoadingState } from '@/components/States';

const SORTS: ReadonlyArray<{ value: CardsSort; label: string }> = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'rarest', label: 'Rarest' },
  { value: 'happiest', label: 'Happiest' },
];

const PAGE_SIZE = 24;

export function DexPage(): ReactElement {
  const navigate = useNavigate();
  const reducedMotion = useReducedMotion();
  const discovered = useDiscoveryStore((s) => s.discovered);
  const revealedThrough = useDiscoveryStore((s) => s.revealedThrough ?? 0);
  const revealThrough = useDiscoveryStore((s) => s.revealThrough);
  const revealTimer = useRef<number>();

  const [rarity, setRarity] = useState<Rarity | undefined>(undefined);
  const [type, setType] = useState<SlimeType | undefined>(undefined);
  const [sort, setSort] = useState<CardsSort>('newest');
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [revealing, setRevealing] = useState(false);
  const [revealWave, setRevealWave] = useState<ReadonlySet<number>>(new Set());
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    const id = window.setTimeout(() => setQ(qInput.trim()), 250);
    return () => window.clearTimeout(id);
  }, [qInput]);

  useEffect(() => {
    setPage(1);
  }, [rarity, type, sort, q]);

  useEffect(
    () => () => {
      if (revealTimer.current !== undefined) {
        window.clearTimeout(revealTimer.current);
      }
    },
    [],
  );

  const query = useMemo(
    () => ({ page, size: PAGE_SIZE, rarity, type, sort, q: q || undefined }),
    [page, rarity, type, sort, q],
  );
  const cards = useCards(query);
  const newest = useCards({ page: 1, size: 1, sort: 'newest' });

  const discoveredSet = useMemo(() => new Set(discovered), [discovered]);
  const total = cards.data?.total ?? 0;
  const items = cards.data?.items ?? [];
  const collectionTotal = newest.data?.total ?? total;
  const latestSerial = newest.data?.items[0]?.serial;
  const allRevealed = latestSerial !== undefined && revealedThrough >= latestSerial;
  const metCount = allRevealed
    ? collectionTotal
    : Math.min(discoveredSet.size, collectionTotal);

  const isRevealed = (serial: number): boolean =>
    serial <= revealedThrough || discoveredSet.has(serial);

  const handleRevealAll = (): void => {
    if (revealing || latestSerial === undefined) return;

    const lockedOnPage = items
      .filter((item) => !isRevealed(item.serial))
      .map((item) => item.serial);
    setRevealWave(new Set(lockedOnPage));
    setRevealing(true);
    setAnnouncement(`Revealing all ${collectionTotal} slimes.`);
    revealThrough(latestSerial);

    const lastDelay = Math.max(0, Math.min(lockedOnPage.length - 1, 23)) * 55;
    revealTimer.current = window.setTimeout(
      () => {
        setRevealWave(new Set());
        setRevealing(false);
        setAnnouncement(`All ${collectionTotal} slimes revealed.`);
      },
      reducedMotion ? 50 : lastDelay + 650,
    );
  };

  return (
    <section aria-labelledby="dex-heading" className="flex flex-col gap-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <h1 id="dex-heading" className="font-pixel text-[22px] text-ink">
          SLIMEDEX
        </h1>
        <p className="font-stat text-[12px] tracking-[2px] text-ink-soft">
          You’ve met {metCount} slimes · {collectionTotal} have bloomed
        </p>
        {collectionTotal > 0 ? (
          <PixelButton
            variant="pink"
            size="sm"
            className={`min-h-11 ${revealing ? 'ps-reveal-all--active' : ''}`}
            onClick={handleRevealAll}
            disabled={allRevealed && !revealing}
            aria-busy={revealing}
            aria-label={
              allRevealed
                ? `All ${collectionTotal} slimes revealed`
                : `Reveal all ${collectionTotal} slimes`
            }
          >
            {revealing ? 'REVEALING...' : allRevealed ? 'ALL REVEALED' : 'REVEAL ALL'}
          </PixelButton>
        ) : null}
        <span className="sr-only" aria-live="polite">
          {announcement}
        </span>
      </header>

      <div className="flex flex-col gap-4 rounded-lg border-4 border-ink bg-paper p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by rarity">
          <FilterPill active={rarity === undefined} onClick={() => setRarity(undefined)}>
            ALL
          </FilterPill>
          {RARITY_ORDER.map((r) => (
            <FilterPill
              key={r}
              active={rarity === r}
              color={tokens.rarity[r].color}
              onClick={() => setRarity(rarity === r ? undefined : r)}
            >
              {r}
            </FilterPill>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 font-stat text-[12px] tracking-[1px] text-ink-soft">
            <span className="sr-only">Search by name</span>
            <input
              type="search"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Search name…"
              className="ps-focusable w-44 rounded-pill border-4 border-ink bg-cream px-4 py-1.5 font-round text-ink placeholder:text-ink-soft"
              aria-label="Search slimes by name"
            />
          </label>

          <label className="flex items-center gap-2 font-stat text-[12px] tracking-[1px] text-ink-soft">
            TYPE
            <select
              value={type ?? ''}
              onChange={(e) => setType((e.target.value || undefined) as SlimeType | undefined)}
              className="ps-focusable rounded-pill border-4 border-ink bg-cream px-3 py-1.5 font-round text-ink"
              aria-label="Filter by type"
            >
              <option value="">All types</option>
              {SLIME_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 font-stat text-[12px] tracking-[1px] text-ink-soft">
            SORT
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as CardsSort)}
              className="ps-focusable rounded-pill border-4 border-ink bg-cream px-3 py-1.5 font-round text-ink"
              aria-label="Sort order"
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {cards.isLoading ? (
        <LoadingState label="Opening the dex…" />
      ) : cards.isError ? (
        <ErrorState onRetry={() => void cards.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {items.map((item, i) => (
            <li
              key={item.serial}
              className={revealWave.has(item.serial) ? 'ps-dex-reveal' : undefined}
              style={
                revealWave.has(item.serial)
                  ? ({
                      '--ps-reveal-delay': `${Math.min(i, 23) * 55}ms`,
                    } as CSSProperties)
                  : undefined
              }
            >
              <SlimeCard
                card={toSlimeCardData(item)}
                locked={!isRevealed(item.serial)}
                index={i}
                onOpen={(serial) => navigate(`/slime/${serial}`)}
              />
            </li>
          ))}
        </ul>
      )}

      {total > PAGE_SIZE ? (
        <nav className="flex items-center justify-center gap-4" aria-label="Pagination">
          <button
            type="button"
            className="ps-focusable rounded-pill border-4 border-ink bg-cream px-4 py-1.5 font-pixel text-[11px] text-ink disabled:opacity-40"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            ← Prev
          </button>
          <span className="font-stat text-[12px] tracking-[2px] text-ink-soft">
            Page {page} of {Math.ceil(total / PAGE_SIZE)}
          </span>
          <button
            type="button"
            className="ps-focusable rounded-pill border-4 border-ink bg-cream px-4 py-1.5 font-pixel text-[11px] text-ink disabled:opacity-40"
            onClick={() => setPage((p) => p + 1)}
            disabled={!cards.data?.hasMore}
          >
            Next →
          </button>
        </nav>
      ) : null}
    </section>
  );
}

interface FilterPillProps {
  active: boolean;
  color?: string;
  onClick: () => void;
  children: ReactNode;
}

function FilterPill({ active, color, onClick, children }: FilterPillProps): ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="ps-focusable rounded-pill border-4 border-ink bg-cream px-3 py-1 font-pixel text-[10px] text-ink transition-transform hover:-translate-y-0.5"
      style={active ? { background: color ?? tokens.color.sunbeam, color: tokens.color.ink } : undefined}
    >
      {children}
    </button>
  );
}

export default DexPage;
