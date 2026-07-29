/**
 * ① TODAY'S BLOOM (`/`).
 *
 * The animated wordmark, a "✦ DAY n ✦" ribbon, a live countdown to the next 10:00
 * Europe/Paris, and today's card face-down as a pulsing pixel card-back. Activating the
 * card (click or keyboard) flips it in 3D with a particle burst; the page background
 * adopts the card's palette, stat bars cascade in, and rarity ≥ EPIC earns a confetti
 * volley and a gentle screen shake. Below sits the RECENTLY BLOOMED strip. Every effect
 * is gated by the design system's useReducedMotion.
 */
import { useEffect, useRef, useState, type ReactElement } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  AnimatedTitle,
  CardFlip,
  Chip,
  Confetti,
  Countdown,
  HoloCard,
  PixelButton,
  RARITY_ORDER,
  RarityBadge,
  Ribbon,
  SlimeCard,
  StatBar,
  TypePill,
  tokens,
  useReducedMotion,
  type ConfettiHandle,
  type StatKey,
} from '@/design';
import { useCard, useCards, useToday } from '@/api/client';
import { ApiRequestError } from '@/api/client';
import { formatMintDate, paletteBackground, toSlimeCardData } from '@/lib/cards';
import { useAmbientStore } from '@/store/ambient';
import { useDiscoveryStore } from '@/store/discovery';
import { SmartImage } from '@/components/SmartImage';
import { ErrorState, LoadingState } from '@/components/States';

const EPIC_INDEX = RARITY_ORDER.indexOf('EPIC');

/**
 * What the home page shows before the day's slime exists.
 *
 * The card sits face down in the rain, the countdown runs to the next 10:00 in Paris,
 * and the copy says the slime is still condensing — because that is what is actually
 * happening. Presenting this as an error would be both wrong and a poor first
 * impression, since it is the state every visitor sees for fourteen hours a day.
 */
/** Decorative floating sparkles. Purely visual, so hidden from assistive tech. */
function Sparkles({ count = 10 }: { count?: number }): ReactElement {
  const reduced = useReducedMotion();
  const marks = ['✦', '✧', '⋆', '✩', '❋'];
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {Array.from({ length: count }, (_, i) => {
        const left = (i * 37) % 92;
        const delay = (i * 0.9) % 7;
        const size = 11 + ((i * 5) % 12);
        return (
          <span
            key={i}
            style={{
              position: 'absolute',
              left: `${left}%`,
              bottom: '-8%',
              fontSize: size,
              color: i % 3 === 0 ? tokens.color.sunbeam : tokens.color.bubblegum,
              opacity: 0.85,
              animation: reduced
                ? 'none'
                : `ps-drift ${9 + (i % 5)}s linear ${delay}s infinite`,
            }}
          >
            {marks[i % marks.length]}
          </span>
        );
      })}
    </div>
  );
}

/**
 * The slime discovered before the one still forming.
 *
 * The waiting page is what a visitor sees for fourteen hours a day, and a lone
 * question mark gives them nothing to look at and no reason to stay. Showing the
 * previous slime in full turns the wait into a hand-off: here is what yesterday
 * produced, and something just like it is on its way.
 */
function PreviousSlime(): ReactElement | null {
  const navigate = useNavigate();
  const reduced = useReducedMotion();
  const recent = useCards({ sort: 'newest', size: 1 });
  const summary = recent.data?.items?.[0];
  const detail = useCard(summary?.serial);
  const card = detail.data;

  if (!summary) return null;

  const palette = card ? paletteBackground(card) : undefined;
  const stats: ReadonlyArray<[StatKey, number]> = card
    ? [
        ['strength', card.strength],
        ['endurance', card.endurance],
        ['agility', card.agility],
        ['happiness', card.happiness],
      ]
    : [];

  return (
    <aside
      aria-labelledby="previous-heading"
      className="relative w-full overflow-hidden rounded-xl border-4 border-ink p-6 shadow-card md:p-8"
      style={{
        background: palette ?? tokens.color.cream,
        animation: reduced ? 'none' : 'ps-bobin .7s var(--ps-pop) both',
      }}
    >
      <Sparkles count={14} />

      <div className="relative flex flex-col items-center gap-6 md:flex-row md:items-center md:gap-8">
        {/* Artwork */}
        <button
          type="button"
          onClick={() => navigate(`/slime/${summary.serial}`)}
          className="ps-focusable w-full max-w-[230px] shrink-0 rounded-lg"
          style={{ animation: reduced ? 'none' : 'ps-breathe 5.5s ease-in-out infinite' }}
          aria-label={`See ${summary.name}, the previously discovered slime`}
        >
          <HoloCard imageAlt={`${summary.name}, a ${summary.rarity} ${summary.type} slime`}>
            <SmartImage
              src={summary.thumbUrl}
              thumb={summary.thumbUrl}
              alt={`${summary.name}, a ${summary.rarity} ${summary.type} slime`}
              sizes="230px"
            />
          </HoloCard>
        </button>

        {/* Identity + stats + actions */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <div className="flex flex-col items-center gap-3 md:items-start">
            <Ribbon icon="✧" tone={tokens.color.mint}>
              PREVIOUSLY DISCOVERED
            </Ribbon>
            <h2 id="previous-heading" className="font-pixel text-[26px] text-ink">
              {summary.name}
            </h2>
            <div className="flex flex-wrap items-center justify-center gap-2 md:justify-start">
              <RarityBadge rarity={summary.rarity} />
              <TypePill type={summary.type} />
              <Chip>LV {summary.level}</Chip>
              {summary.shiny ? (
                <Chip tone={tokens.color.sunbeam} icon="✨">
                  SHINY
                </Chip>
              ) : null}
              {typeof card?.smileYield === 'number' ? (
                <Chip tone={tokens.color.sky} icon="✨">
                  +{card.smileYield.toLocaleString()} $SMILE
                </Chip>
              ) : null}
              {summary.onChain ? (
                <Chip tone={tokens.color.mint} icon="⛓">
                  ON-CHAIN
                </Chip>
              ) : null}
            </div>
          </div>

          {stats.length > 0 ? (
            <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {stats.map(([stat, value], i) => (
                <StatBar key={stat} stat={stat} value={value} index={i} />
              ))}
            </div>
          ) : null}

          {card?.quote ? (
            <p className="text-center font-stat text-[13px] italic text-ink-soft md:text-left">
              “{card.quote}”
            </p>
          ) : null}

          <div className="flex flex-wrap items-center justify-center gap-3 md:justify-start">
            <PixelButton variant="ghost" onClick={() => navigate(`/slime/${summary.serial}`)}>
              ✦ MEET {summary.name.toUpperCase()}
            </PixelButton>
            <span className="font-stat text-[11px] tracking-[1px] text-ink-soft">
              {summary.cardId} · {formatMintDate(summary.mintDate)}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function PreBloom(): ReactElement {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center gap-10">
      <section className="ps-hero w-full">
        <AnimatedTitle text="PIXELSLIME" eyebrow="PUNIPUNI PARADISE" />
      </section>

      <Ribbon>✦ THE PIXEL RAIN IS FALLING ✦</Ribbon>

      <div className="grid w-full gap-8 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-center">
        <div className="order-2 min-w-0 lg:order-1">
          <PreviousSlime />
        </div>

        <div className="order-1 flex flex-col items-center gap-6 lg:order-2">
        <div
          role="img"
          aria-label="Today's slime has not bloomed yet"
        style={{
          position: 'relative',
          width: 'min(360px, 80vw)',
          aspectRatio: '1024 / 1536',
          display: 'grid',
          placeItems: 'center',
          borderRadius: tokens.radius.lg,
          border: `6px solid ${tokens.color.ink}`,
          boxShadow: tokens.shadow.card,
          background: `radial-gradient(circle at 50% 38%, rgba(255,255,255,.30), transparent 58%),
            repeating-linear-gradient(45deg, #6C4FD6 0 16px, #7B5CE6 16px 32px)`,
        }}
      >
        <span
          style={{
            position: 'absolute',
            top: 22,
            fontFamily: tokens.font.pixel,
            fontSize: 10,
            letterSpacing: 2,
            color: tokens.color.sunbeam,
          }}
        >
          ✦ PIXEL RAIN ✦
        </span>
        <span
          style={{
            fontFamily: tokens.font.pixel,
            fontSize: 68,
            color: '#FFFFFF',
            textShadow: '0 7px 0 rgba(0,0,0,.32)',
          }}
        >
          ?
        </span>
        <span
          style={{
            position: 'absolute',
            bottom: 26,
            fontFamily: tokens.font.stat,
            fontSize: 13,
            letterSpacing: 2,
            color: '#FFFFFF',
            opacity: 0.9,
          }}
        >
          STILL CONDENSING
        </span>
        </div>

        <Countdown label="NEXT SLIME IN" />
        </div>
      </div>

      <p
        className="max-w-xl text-center"
        style={{ fontFamily: tokens.font.round, color: tokens.color.inkSoft, lineHeight: 1.7 }}
      >
        Every dawn, exactly <b>one</b> new slime condenses out of the Great Pixel Rain.
        Today’s has not finished forming — come back at <b>10:00 Paris</b> and it will be
        waiting, face down, for you to turn over.
      </p>

      <PixelButton variant="ghost" onClick={() => navigate('/dex')}>
        ▦ BROWSE THE SLIMEDEX
      </PixelButton>
    </div>
  );
}

export function TodayPage(): ReactElement {
  const today = useToday();
  const recent = useCards({ sort: 'newest', size: 8 });
  const reduced = useReducedMotion();
  const navigate = useNavigate();
  const confettiRef = useRef<ConfettiHandle>(null);
  const shakeRef = useRef<HTMLDivElement>(null);
  const setTint = useAmbientStore((s) => s.setTint);
  const discover = useDiscoveryStore((s) => s.discover);
  const [revealed, setRevealed] = useState(false);

  const data = today.data;
  const card = data?.card;

  useEffect(() => () => setTint(null), [setTint]);

  const handleReveal = (): void => {
    if (!card) return;
    setRevealed(true);
    discover(card.serial);
    setTint(paletteBackground(card));
    if (reduced) return;
    const isCeremony = RARITY_ORDER.indexOf(card.rarity) >= EPIC_INDEX;
    confettiRef.current?.fire({ x: 0.5, y: 0.42 });
    if (isCeremony) {
      window.setTimeout(() => confettiRef.current?.fire({ x: 0.32, y: 0.5 }), 140);
      window.setTimeout(() => confettiRef.current?.fire({ x: 0.68, y: 0.5 }), 260);
      shakeRef.current?.animate(
        [
          { transform: 'translateX(0)' },
          { transform: 'translateX(-8px) rotate(-1deg)' },
          { transform: 'translateX(7px) rotate(1deg)' },
          { transform: 'translateX(-5px)' },
          { transform: 'translateX(0)' },
        ],
        { duration: 520, easing: 'ease-in-out' },
      );
    }
  };

  if (today.isLoading) return <LoadingState label="Today’s bloom is opening…" />;

  // A 404 is not a failure: it means the Pixel Rain has not condensed today's slime yet.
  // Every fresh deployment hits this on day one, and so does every visitor between
  // midnight and 10:00 Paris, so it deserves the ceremony rather than an error panel.
  // The countdown is computed client-side because the endpoint that would carry it is
  // the very one returning 404.
  const notBloomedYet =
    today.error instanceof ApiRequestError && today.error.status === 404;

  if (notBloomedYet) return <PreBloom />;

  if (today.isError || !data || !card) {
    return <ErrorState label="Today’s bloom hasn’t arrived." onRetry={() => void today.refetch()} />;
  }

  const stats: ReadonlyArray<[StatKey, number]> = [
    ['strength', card.strength],
    ['endurance', card.endurance],
    ['agility', card.agility],
    ['happiness', card.happiness],
  ];

  const recentItems = (recent.data?.items ?? []).filter((c) => c.serial !== card.serial).slice(0, 6);

  return (
    <div className="flex flex-col items-center gap-10">
      <Confetti ref={confettiRef} />

      <section className="ps-hero w-full">
        <AnimatedTitle
          text="PIXELSLIME"
          eyebrow="PUNIPUNI PARADISE"
          subtitle="TODAY’S BLOOM HAS ARRIVED"
          rainbow={card.rarity === 'MYTHIC'}
        />
        <div className="mt-6 flex flex-wrap items-center justify-center gap-4">
          <Ribbon icon="✦" tone={tokens.color.bubblegum}>
            DAY {data.dayNumber}
          </Ribbon>
          <Countdown target={new Date(data.nextBloomAt)} label="NEXT SLIME IN" />
        </div>
      </section>

      <div className="grid w-full gap-8 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        {/* The collection so far, laid out along the left so it reads before the fold. */}
        <section
          className="order-2 min-w-0 lg:order-1"
          aria-labelledby="recent-heading"
        >
          <h2
            id="recent-heading"
            className="mb-4 text-center font-pixel text-[15px] text-ink lg:text-left"
          >
            RECENTLY BLOOMED
          </h2>
          {recentItems.length === 0 ? (
            <p className="text-center font-stat text-[12px] tracking-[2px] text-ink-soft lg:text-left">
              The garden is just getting started — today’s is the very first.
            </p>
          ) : (
            // A horizontal rail rather than a grid: with two slimes a six-column grid
            // left one card marooned beside five empty cells. A rail is honest at any
            // count, and scrolls sideways instead of pushing the card below the fold.
            <ul className="flex snap-x gap-4 overflow-x-auto pb-3">
              {recentItems.map((item, i) => (
                <li key={item.serial} className="w-[168px] shrink-0 snap-start">
                  <SlimeCard
                    card={toSlimeCardData(item)}
                    index={i}
                    isNew={i === 0}
                    onOpen={(serial) => navigate(`/slime/${serial}`)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>

        <div ref={shakeRef} className="order-1 w-full max-w-[340px] justify-self-center lg:order-2">
          <CardFlip
            onReveal={handleReveal}
            seal="✦ PIXEL RAIN ✦"
            hint="CLICK OR PRESS ENTER"
            revealedLabel={`${card.name}, ${card.rarity} ${card.type} — today’s bloom`}
          >
            <SmartImage
              src={card.imageUrl}
              thumb={card.thumbUrl}
              alt={`${card.name}, a ${card.rarity} ${card.type} slime`}
              sizes="(max-width: 640px) 88vw, 340px"
              eager
            />
          </CardFlip>
        </div>
      </div>

      {revealed ? (
        <section
          className="w-full max-w-2xl rounded-xl border-4 border-ink bg-paper p-6 shadow-card animate-fade-up"
          aria-label={`${card.name} details`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-pixel text-[20px] text-ink">{card.name}</h2>
              <p className="mt-1 font-stat text-[12px] tracking-[2px] text-ink-soft">
                {card.cardId} · LV {card.level} · {formatMintDate(card.mintDate)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <RarityBadge rarity={card.rarity} />
              <TypePill type={card.type} />
            </div>
          </div>

          <p className="mt-4 font-round text-ink">{card.personality}</p>
          <p className="mt-2 font-stat text-[13px] italic text-ink-soft">“{card.quote}”</p>

          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {stats.map(([stat, value], i) => (
              <StatBar key={stat} stat={stat} value={value} index={i} />
            ))}
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <PixelButton variant="sunbeam" onClick={() => navigate(`/slime/${card.serial}`)}>
              See the stored bytes →
            </PixelButton>
            <Link to="/dex" className="ps-focusable">
              <PixelButton variant="ghost">Browse the SLIMEDEX</PixelButton>
            </Link>
          </div>
        </section>
      ) : (
        <p className="max-w-md text-center font-stat text-[13px] tracking-[2px] text-ink-soft">
          A brand-new slime blooms every day at 10:00 Paris time. Flip today’s card to meet it.
        </p>
      )}
    </div>
  );
}

export default TodayPage;
