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
import { useCards, useToday } from '@/api/client';
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

/**
 * The collection so far, as a horizontal rail.
 *
 * Shared by the waiting page and the bloomed page so the layout does not rearrange
 * itself at 10:00. A rail rather than a fixed grid: with two slimes a six-column grid
 * leaves one card marooned beside five empty cells, which reads as broken rather than
 * as early. A rail looks deliberate at two and scrolls sideways at fifty.
 */
function RecentRail({ excludeSerial }: { excludeSerial?: number }): ReactElement {
  const navigate = useNavigate();
  const recent = useCards({ sort: 'newest', size: 12 });
  const items = (recent.data?.items ?? [])
    .filter((c) => c.serial !== excludeSerial)
    .slice(0, 10);

  return (
    <section className="w-full" aria-labelledby="recent-heading">
      <div className="mb-1 flex items-center gap-4">
        <h2 id="recent-heading" className="shrink-0 font-pixel text-[15px] text-ink">
          RECENTLY BLOOMED
        </h2>
        <span
          aria-hidden
          className="h-[6px] flex-1 rounded-pill"
          style={{
            background: `repeating-linear-gradient(90deg, ${tokens.color.bubblegum} 0 14px, ${tokens.color.sunbeam} 14px 28px, ${tokens.color.mint} 28px 42px, ${tokens.color.sky} 42px 56px)`,
          }}
        />
      </div>
      <p className="mb-4 font-stat text-[12px] tracking-[1px] text-ink-soft">
        The last slimes to fall out of the Rain.
      </p>
      {items.length === 0 ? (
        <p className="font-stat text-[12px] tracking-[2px] text-ink-soft">
          The garden is just getting started.
        </p>
      ) : (
        <ul className="flex snap-x gap-4 overflow-x-auto pb-3">
          {items.map((item, i) => (
            <li key={item.serial} className="w-[178px] shrink-0 snap-start">
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

      <div className="grid w-full gap-8 lg:grid-cols-[360px_minmax(0,1fr)] lg:items-start">
        <div className="w-full max-w-[360px] justify-self-center lg:justify-self-start">
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
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          <Countdown label="NEXT SLIME IN" />

          <h2 className="font-pixel text-[30px] leading-tight text-ink">Today’s Bloom:</h2>
          <p
            aria-hidden
            className="font-pixel text-[30px] leading-tight"
            style={{ color: tokens.color.bubblegum, letterSpacing: '0.18em' }}
          >
            ?????
          </p>
          <p className="max-w-lg font-round text-ink-soft" style={{ lineHeight: 1.7 }}>
            Every dawn, exactly <b>one</b> new slime condenses out of the Great Pixel Rain.
            Today’s has not finished forming — come back at <b>10:00 Paris</b> and it will be
            waiting, face down, for you to turn over.
          </p>
          <div className="flex flex-wrap gap-3">
            <PixelButton variant="ghost" onClick={() => navigate('/dex')}>
              ▦ BROWSE THE SLIMEDEX
            </PixelButton>
          </div>
        </div>
      </div>

      <RecentRail />
    </div>
  );
}

export function TodayPage(): ReactElement {
  const today = useToday();
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


  return (
    <div className="flex flex-col gap-10">
      <Confetti ref={confettiRef} />

      <section className="ps-hero w-full">
        <AnimatedTitle
          text="PIXELSLIME"
          eyebrow="PUNIPUNI PARADISE"
          subtitle="TODAY’S BLOOM HAS ARRIVED"
          rainbow={card.rarity === 'MYTHIC'}
        />
      </section>

      {/* Card on the left, everything about it on the right — the mockup's layout.
          Anything else leaves the right half of the fold empty, which is what the
          previous arrangement did. */}
      <div className="grid w-full gap-8 lg:grid-cols-[360px_minmax(0,1fr)] lg:items-start">
        <div ref={shakeRef} className="w-full max-w-[360px] justify-self-center lg:justify-self-start">
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
              sizes="(max-width: 640px) 88vw, 360px"
              eager
            />
          </CardFlip>
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          <div className="flex flex-wrap items-center gap-3">
            <Ribbon icon="✦" tone={tokens.color.bubblegum}>
              DAY {data.dayNumber} · {formatMintDate(card.mintDate).toUpperCase()}
            </Ribbon>
            <Countdown target={new Date(data.nextBloomAt)} label="NEXT SLIME IN" />
          </div>

          {revealed ? (
            <div className="flex flex-col gap-4 animate-fade-up">
              <div>
                <h2 className="font-pixel text-[30px] leading-tight text-ink">{card.name}</h2>
                <p className="mt-2 font-stat text-[12px] tracking-[2px] text-ink-soft">
                  {card.cardId} · LV {card.level}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <RarityBadge rarity={card.rarity} />
                <TypePill type={card.type} />
                {card.shiny ? (
                  <Chip tone={tokens.color.sunbeam} icon="✨">
                    SHINY
                  </Chip>
                ) : null}
                {typeof card.smileYield === 'number' ? (
                  <Chip tone={tokens.color.sky} icon="✨">
                    +{card.smileYield.toLocaleString()} $SMILE
                  </Chip>
                ) : null}
                {card.onChain ? (
                  <Chip tone={tokens.color.mint} icon="⛓">
                    ON-CHAIN
                  </Chip>
                ) : null}
              </div>

              <p className="font-round text-ink">{card.personality}</p>
              <p className="font-stat text-[13px] italic text-ink-soft">“{card.quote}”</p>

              <div className="grid gap-2 sm:grid-cols-2">
                {stats.map(([stat, value], i) => (
                  <StatBar key={stat} stat={stat} value={value} index={i} />
                ))}
              </div>

              <div className="flex flex-wrap gap-3">
                <PixelButton variant="sunbeam" onClick={() => navigate(`/slime/${card.serial}`)}>
                  ◆ VIEW PROFILE
                </PixelButton>
                <Link to="/dex" className="ps-focusable">
                  <PixelButton variant="ghost">▦ OPEN SLIMEDEX</PixelButton>
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              <h2 className="font-pixel text-[30px] leading-tight text-ink">
                Today’s Bloom:
              </h2>
              <p
                aria-hidden
                className="font-pixel text-[30px] leading-tight"
                style={{ color: tokens.color.bubblegum, letterSpacing: '0.18em' }}
              >
                ?????
              </p>
              <p className="max-w-lg font-round text-ink-soft" style={{ lineHeight: 1.7 }}>
                A new slime has condensed out of the Pixel Rain. Turn the card over to
                catalogue it in the SLIMEDEX before it drifts away…
              </p>
              <div className="flex flex-wrap gap-3">
                <PixelButton variant="sunbeam" onClick={handleReveal}>
                  ◆ REVEAL TODAY’S SLIME
                </PixelButton>
                <Link to="/dex" className="ps-focusable">
                  <PixelButton variant="ghost">▦ OPEN SLIMEDEX</PixelButton>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      <RecentRail excludeSerial={card.serial} />
    </div>
  );
}

export default TodayPage;
