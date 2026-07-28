import type { CSSProperties, ReactElement } from 'react';
import { color } from '../tokens';
import type { StatKey } from '../types';
import { shade } from '../lib/color';

/**
 * <StatBar/> — an animated segmented stat bar, one per battle stat. Each stat has
 * its own colour and icon (matching the mochibo card art); the lit segments pop in
 * on mount with a stagger. It is a real progressbar for assistive tech; the numeric
 * value is always shown, so the segments are purely decorative. Under reduced motion
 * the segments simply appear (handled centrally in globals.css).
 */

export interface StatBarProps {
  stat: StatKey;
  /** 0–100. */
  value: number;
  /** Overrides the default upper-cased stat name. */
  label?: string;
  /** Number of segments. Defaults to 10 (each segment ≈ 10 points). */
  segments?: number;
  /** Position within a group, to cascade several bars. */
  index?: number;
  /** Disable the pop-in animation. */
  animate?: boolean;
  className?: string;
}

interface StatMeta {
  icon: string;
  base: string;
  label: string;
}

const STAT_META: Record<StatKey, StatMeta> = {
  strength: { icon: '💪', base: color.coral, label: 'STRENGTH' },
  endurance: { icon: '🛡', base: color.mint, label: 'ENDURANCE' },
  agility: { icon: '🪽', base: color.sky, label: 'AGILITY' },
  happiness: { icon: '💖', base: color.bubblegum, label: 'HAPPINESS' },
};

export function StatBar({
  stat,
  value,
  label,
  segments = 10,
  index = 0,
  animate = true,
  className,
}: StatBarProps): ReactElement {
  const meta = STAT_META[stat];
  const clamped = Math.max(0, Math.min(100, value));
  const lit = Math.round((clamped / 100) * segments);
  const litFill = `linear-gradient(180deg, ${shade(meta.base, 34)}, ${meta.base})`;
  const text = label ?? meta.label;
  const classes = ['ps-stat', className ?? ''].filter(Boolean).join(' ');

  return (
    <div
      className={classes}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`${text} ${clamped} of 100`}
    >
      <span className="ps-stat__lbl">
        <span aria-hidden="true">{meta.icon}</span>
        {text}
      </span>
      <div className="ps-stat__track" aria-hidden="true">
        {Array.from({ length: segments }, (_, i) => {
          const on = i < lit;
          const style: CSSProperties = on
            ? {
                background: litFill,
                ...(animate ? { animationDelay: `${index * 140 + i * 45}ms` } : {}),
              }
            : {};
          return (
            <span
              key={i}
              className={`ps-stat__seg${on && animate ? ' ps-stat__seg--on' : ''}`}
              style={style}
            />
          );
        })}
      </div>
      <span className="ps-stat__val">{clamped}</span>
    </div>
  );
}

export default StatBar;
