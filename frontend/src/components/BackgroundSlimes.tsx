/**
 * The drifting ambient slimes behind every screen — the mockup's signature backdrop.
 * Uses the design system's `.ps-bgslimes`/`.ps-drift` container (which the central
 * reduced-motion rule already quietens) so we never re-implement motion gating.
 */
import { useMemo, type ReactElement } from 'react';
import { SlimeSprite, tokens, type SlimeAccessory, type SlimeFace } from '@/design';

interface Drifter {
  color: string;
  accessory: SlimeAccessory;
  face: SlimeFace;
  size: number;
  left: string;
  duration: string;
  delay: string;
}

const PALETTE = [
  tokens.color.bubblegum,
  tokens.color.mint,
  tokens.color.sky,
  tokens.color.grape,
  tokens.color.sunbeam,
  tokens.color.coral,
];
const ACCESSORIES: SlimeAccessory[] = ['flower', 'leaf', 'star', 'none', 'horn', 'none'];
const FACES: SlimeFace[] = ['happy', 'sleepy', 'smug'];

function buildDrifters(count: number): Drifter[] {
  const out: Drifter[] = [];
  for (let i = 0; i < count; i += 1) {
    out.push({
      color: PALETTE[i % PALETTE.length],
      accessory: ACCESSORIES[i % ACCESSORIES.length],
      face: FACES[i % FACES.length],
      size: 46 + ((i * 37) % 60),
      left: `${(i * 137) % 92}%`,
      duration: `${16 + ((i * 7) % 14)}s`,
      delay: `${-(i * 5) % 20}s`,
    });
  }
  return out;
}

export function BackgroundSlimes({ count = 7 }: { count?: number }): ReactElement {
  const drifters = useMemo(() => buildDrifters(count), [count]);
  return (
    <div className="ps-bgslimes" aria-hidden>
      {drifters.map((d, i) => (
        <span
          key={i}
          className="ps-drift"
          style={{ left: d.left, bottom: '-90px', animationDuration: d.duration, animationDelay: d.delay }}
        >
          <SlimeSprite baseColor={d.color} accessory={d.accessory} face={d.face} size={d.size} />
        </span>
      ))}
    </div>
  );
}

export default BackgroundSlimes;
