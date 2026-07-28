import { useEffect, useState } from 'react';
import type { ReactNode, ReactElement } from 'react';

/**
 * <Countdown/> — the "NEXT SLIME IN 07:12:44" clock. Ticks once a second and always
 * cleans up its interval on unmount. By default it counts to the next occurrence of
 * the daily publish hour (10:00 local), rolling to tomorrow once it passes, exactly
 * like the mockup; pass `target` for a fixed one-shot deadline instead.
 */

export interface CountdownProps {
  /** Fixed deadline. When omitted, counts to the next `hour`:00 local time. */
  target?: Date;
  /** Daily publish hour (0–23) used when `target` is omitted. Defaults to 10. */
  hour?: number;
  /** Leading label. Defaults to "NEXT SLIME IN". */
  label?: ReactNode;
  /** Fired once when a fixed `target` deadline is reached. */
  onComplete?: () => void;
  className?: string;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function nextDailyDeadline(hour: number, now: Date): Date {
  const next = new Date(now);
  next.setHours(hour, 0, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  return next;
}

function format(msRemaining: number): string {
  const ms = Math.max(0, msRemaining);
  const h = Math.floor(ms / 3.6e6);
  const m = Math.floor(ms / 6e4) % 60;
  const s = Math.floor(ms / 1e3) % 60;
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

export function Countdown({
  target,
  hour = 10,
  label = 'NEXT SLIME IN',
  onComplete,
  className,
}: CountdownProps): ReactElement {
  const [display, setDisplay] = useState<string>('--:--:--');

  useEffect(() => {
    let done = false;
    const tick = (): void => {
      const now = new Date();
      const deadline = target ?? nextDailyDeadline(hour, now);
      const remaining = deadline.getTime() - now.getTime();
      setDisplay(format(remaining));
      if (target && remaining <= 0 && !done) {
        done = true;
        onComplete?.();
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [target, hour, onComplete]);

  const classes = ['ps-countdown', className ?? ''].filter(Boolean).join(' ');
  return (
    <span className={classes} aria-label={`${String(label)} ${display}`}>
      {label}
      <b>{display}</b>
    </span>
  );
}

export default Countdown;
