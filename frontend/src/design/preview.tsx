import { useRef, useState } from 'react';
import type { ReactElement, ReactNode } from 'react';
import mochibo from './preview-assets/mochibo.png';
import {
  AnimatedTitle,
  CardFlip,
  Chip,
  Confetti,
  Countdown,
  HoloCard,
  PixelButton,
  RarityBadge,
  Ribbon,
  SlimeCard,
  SlimeSprite,
  StatBar,
  TypePill,
  RARITY_ORDER,
  SLIME_TYPES,
} from './index';
import type { ConfettiHandle, SlimeCardData, SlimeAccessory, SlimeFace } from './index';

/**
 * <Preview/> — a single page that renders every design-system component in every
 * meaningful state, so a human (and Playwright) can eyeball the whole system at once.
 * W6 wires this to a `/design` route. It is intentionally self-contained: the one
 * real card image lives in ./preview-assets, everything else is procedural.
 */

type Sample = SlimeCardData & { locked?: boolean; isNew?: boolean };

const SAMPLES: Sample[] = [
  { serial: 1, name: 'Mochibo', rarity: 'EPIC', type: 'FAIRY', level: 12, imageSrc: mochibo, spriteColor: '#FF9EC4', accessory: 'flower', face: 'happy', isNew: true },
  { serial: 2, name: 'Fernwick', rarity: 'COMMON', type: 'FOREST', level: 8, spriteColor: '#7FCB93', accessory: 'leaf', face: 'sleepy' },
  { serial: 3, name: 'Blorbit', rarity: 'LEGENDARY', type: 'COSMIC', level: 19, spriteColor: '#7C6BE0', accessory: 'star', face: 'happy' },
  { serial: 5, name: 'Kinaco', rarity: 'RARE', type: 'SUGAR', level: 14, spriteColor: '#F3C98B', accessory: 'none', face: 'smug' },
  { serial: 8, name: 'Glimmerpuff', rarity: 'MYTHIC', type: 'DREAM', level: 22, spriteColor: '#FFA8DE', accessory: 'star', face: 'happy' },
  { serial: 10, name: 'Zapkin', rarity: 'UNCOMMON', type: 'STORM', level: 13, spriteColor: '#9B87F0', accessory: 'none', face: 'happy' },
  { serial: 7, name: 'Nibblewisp', rarity: 'EPIC', type: 'GHOST', level: 16, spriteColor: '#B6ADE2', accessory: 'horn', face: 'sleepy', locked: true },
  // Deliberately broken artwork URL: proves the onError → procedural sprite fallback.
  { serial: 11, name: 'Patchwork', rarity: 'RARE', type: 'PAPER', level: 9, imageSrc: './preview-assets/missing-404.png', spriteColor: '#E8D9B8', accessory: 'leaf', face: 'smug' },
];

const SPRITE_SHOWCASE: Array<{ color: string; accessory: SlimeAccessory; face: SlimeFace }> = [
  { color: '#FF9EC4', accessory: 'flower', face: 'happy' },
  { color: '#7FCB93', accessory: 'leaf', face: 'sleepy' },
  { color: '#7C6BE0', accessory: 'star', face: 'happy' },
  { color: '#B6ADE2', accessory: 'horn', face: 'smug' },
  { color: '#63BEEA', accessory: 'none', face: 'happy' },
  { color: '#F3C98B', accessory: 'none', face: 'smug' },
];

function Section({ title, sub, children }: { title: string; sub?: string; children: ReactNode }): ReactElement {
  return (
    <section className="mb-14">
      <h2
        className="font-pixel text-ink flex items-center gap-3"
        style={{ fontSize: 18, marginBottom: sub ? 6 : 20 }}
      >
        <span>{title}</span>
        <span
          className="rounded-pill"
          style={{
            flex: 1,
            height: 5,
            background:
              'repeating-linear-gradient(90deg,var(--ps-bubblegum) 0 14px,var(--ps-sunbeam) 14px 28px,var(--ps-mint) 28px 42px)',
          }}
        />
      </h2>
      {sub ? <p className="text-ink-soft font-bold mb-5">{sub}</p> : null}
      {children}
    </section>
  );
}

export function Preview(): ReactElement {
  const [night, setNight] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [opened, setOpened] = useState<string | null>(null);
  const confettiRef = useRef<ConfettiHandle>(null);

  const toggleTheme = (): void => {
    const next = !night;
    setNight(next);
    document.documentElement.dataset.theme = next ? 'night' : '';
  };

  return (
    <div className="ps-surface" style={{ minHeight: '100vh' }}>
      <Confetti ref={confettiRef} />

      <div style={{ maxWidth: 1240, margin: '0 auto', padding: '28px 22px 120px' }}>
        {/* ── Top bar ─────────────────────────────────────────────── */}
        <header>
        <div className="flex items-center gap-3" style={{ marginBottom: 8 }}>
          <SlimeSprite baseColor="#FF9EC4" accessory="flower" size={40} />
          <span className="font-pixel" style={{ fontSize: 13, letterSpacing: 1 }}>
            PIXELSLIME · DESIGN SYSTEM
          </span>
          <div className="ml-auto flex items-center gap-2">
            <PixelButton variant="mint" size="sm" onClick={() => confettiRef.current?.fire({ x: 0.5, y: 0.4 })}>
              🎉 CONFETTI
            </PixelButton>
            <PixelButton variant="ghost" size="sm" onClick={toggleTheme} aria-label="Toggle Moonlit Puniverse dark theme">
              {night ? '☀️ DAY' : '🌙 NIGHT'}
            </PixelButton>
          </div>
        </div>
        <p className="text-ink-soft font-bold" style={{ fontSize: 13, marginBottom: 30 }}>
          Every component, every state. Animations honour <code>prefers-reduced-motion</code> (degrade to a fade).
        </p>
        </header>

        <main>
        {/* ── Animated title ──────────────────────────────────────── */}
        <Section title="ANIMATED TITLE">
          <div style={{ display: 'grid', gap: 28 }}>
            <AnimatedTitle as="h1" />
            <AnimatedTitle as="h2" text="PIXELSLIME" eyebrow="✦ MYTHIC DAY ✦" subtitle="DREAMDROP MODE" rainbow />
          </div>
        </Section>

        {/* ── Today's bloom hero ──────────────────────────────────── */}
        <Section title="TODAY'S BLOOM" sub="The card flip is the emotional centrepiece — click or press Enter on it.">
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,340px) minmax(0,1fr)', gap: 40, alignItems: 'center' }} className="today-grid">
            <CardFlip
              imageSrc={mochibo}
              imageAlt="Mochibo — PixelSlime card"
              revealedLabel="Mochibo, EPIC Aurora, FAIRY type"
              onReveal={() => {
                setRevealed(true);
                confettiRef.current?.fire({ x: 0.28, y: 0.45 });
              }}
            />
            <div>
              <div className="flex items-center gap-3" style={{ flexWrap: 'wrap', marginBottom: 16 }}>
                <Ribbon icon="✦">DAY 1 · 28 JUL 2026</Ribbon>
                <Countdown />
              </div>
              <h3 className="font-pixel" style={{ fontSize: 26, lineHeight: 1.35, marginBottom: 12 }}>
                Today's Bloom:{' '}
                <span style={{ color: revealed ? 'var(--ps-grape)' : 'var(--ps-bubblegum)' }}>
                  {revealed ? 'Mochibo' : '? ? ? ? ?'}
                </span>
              </h3>
              <div className="flex gap-2" style={{ flexWrap: 'wrap', marginBottom: 18 }}>
                <TypePill type="FAIRY" icon="💗" />
                <RarityBadge rarity="EPIC" />
                <Chip tone="var(--ps-sunbeam)">LV. 12</Chip>
                <Chip>0.28 m</Chip>
                <Chip>0.9 kg</Chip>
              </div>
              <div style={{ display: 'grid', gap: 12, maxWidth: 460 }}>
                <StatBar stat="strength" value={28} index={0} />
                <StatBar stat="endurance" value={55} index={1} />
                <StatBar stat="agility" value={65} index={2} />
                <StatBar stat="happiness" value={95} index={3} />
              </div>
              <div className="flex gap-3" style={{ flexWrap: 'wrap', marginTop: 24 }}>
                <PixelButton variant="pink" iconLeft="◈">VIEW PROFILE</PixelButton>
                <PixelButton variant="ghost" iconLeft="▦">OPEN SLIMEDEX</PixelButton>
              </div>
            </div>
          </div>
        </Section>

        {/* ── Slimedex grid ───────────────────────────────────────── */}
        <Section title="SLIMEDEX" sub={opened ? `Opened ${opened}` : 'Hover to lift & tilt; the holo sheen scales with rarity. The locked tile hides its tier entirely; the last tile has a dead image URL and falls back to its sprite.'}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(196px,1fr))', gap: 24 }}>
            {SAMPLES.map((c, i) => (
              <SlimeCard
                key={c.serial}
                card={c}
                locked={c.locked}
                isNew={c.isNew}
                index={i}
                onOpen={(serial) => setOpened(`PS-${String(serial).padStart(4, '0')}`)}
              />
            ))}
          </div>
        </Section>

        {/* ── Holo card ───────────────────────────────────────────── */}
        <Section title="HOLO CARD" sub="Pointer/gyroscope tilt with a tracking glare, for the SLIME PROFILE.">
          <div style={{ maxWidth: 320 }}>
            <HoloCard imageSrc={mochibo} imageAlt="Mochibo — holographic" />
          </div>
        </Section>

        {/* ── Rarity & type ───────────────────────────────────────── */}
        <Section title="RARITY BADGES">
          <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
            {RARITY_ORDER.map((r) => (
              <RarityBadge key={r} rarity={r} />
            ))}
          </div>
          <div className="flex gap-2" style={{ flexWrap: 'wrap', marginTop: 12 }}>
            {RARITY_ORDER.map((r) => (
              <RarityBadge key={r} rarity={r} format="house" size="sm" />
            ))}
          </div>
        </Section>

        <Section title="THE 16 TYPES">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(112px,1fr))', gap: 10 }}>
            {SLIME_TYPES.map((t) => (
              <TypePill key={t} type={t} />
            ))}
          </div>
        </Section>

        {/* ── Stat bars ───────────────────────────────────────────── */}
        <Section title="STAT BARS" sub="Segmented, colour + icon per stat, staggered fill on mount.">
          <div style={{ display: 'grid', gap: 12, maxWidth: 480 }}>
            <StatBar stat="strength" value={34} index={0} />
            <StatBar stat="endurance" value={77} index={1} />
            <StatBar stat="agility" value={14} index={2} />
            <StatBar stat="happiness" value={99} index={3} />
          </div>
        </Section>

        {/* ── Buttons ─────────────────────────────────────────────── */}
        <Section title="PIXEL BUTTONS" sub="Chunky 0·6px·0 press-down shadow. Icon-only buttons carry an aria-label.">
          <div className="flex gap-3" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
            <PixelButton variant="sunbeam">SUNBEAM</PixelButton>
            <PixelButton variant="pink">BUBBLEGUM</PixelButton>
            <PixelButton variant="mint">MINT</PixelButton>
            <PixelButton variant="coral">CORAL</PixelButton>
            <PixelButton variant="ghost">GHOST</PixelButton>
            <PixelButton variant="sunbeam" size="sm">SMALL</PixelButton>
            <PixelButton variant="pink" disabled>DISABLED</PixelButton>
            <PixelButton variant="ghost" aria-label="Moonlit Puniverse">🌙</PixelButton>
          </div>
        </Section>

        {/* ── Chips, ribbons, countdown ───────────────────────────── */}
        <Section title="CHIPS · RIBBONS · COUNTDOWN">
          <div className="flex gap-2" style={{ flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>
            <Chip>PLAIN</Chip>
            <Chip icon="🌿" tone="var(--ps-mint)">BIOME</Chip>
            <Chip tone="var(--ps-sky)">0.28 m</Chip>
            <Chip tone="var(--ps-sunbeam)">LV. 42</Chip>
          </div>
          <div className="flex gap-3" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
            <Ribbon icon="✦">DAY 42 · STREAK 7</Ribbon>
            <Ribbon tone="var(--ps-grape)">STEP 2</Ribbon>
            <Countdown />
            <Countdown label="ADOPTION ENDS" hour={18} />
          </div>
        </Section>

        {/* ── Sprite gallery ──────────────────────────────────────── */}
        <Section title="PROCEDURAL SPRITES" sub="16×12 crisp-edge pixel art — one base colour drives light & shadow.">
          <div className="flex gap-6" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
            {SPRITE_SHOWCASE.map((s, i) => (
              <div key={i} style={{ display: 'grid', placeItems: 'center', gap: 8 }}>
                <SlimeSprite baseColor={s.color} accessory={s.accessory} face={s.face} size={84} bob title={`${s.accessory} slime, ${s.face}`} />
                <span className="font-stat" style={{ fontSize: 12, color: 'var(--ps-ink-soft)' }}>
                  {s.accessory}/{s.face}
                </span>
              </div>
            ))}
          </div>
        </Section>

        </main>

        <footer className="font-stat" style={{ fontSize: 13, color: 'var(--ps-ink-soft)', textAlign: 'center', paddingTop: 20 }}>
          PIXELSLIME · PUNIPUNI PARADISE — design system preview · made with 🫧 in the Puniverse
        </footer>
      </div>
    </div>
  );
}

export default Preview;
