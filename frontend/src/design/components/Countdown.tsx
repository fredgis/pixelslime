import { useEffect, useState } from 'react';
import type { ReactNode, ReactElement } from 'react';

/**
 * <Countdown/> — the "NEXT SLIME IN 07:12:44" clock. Ticks once a second and always
 * cleans up its interval on unmount. By default it counts to the next occurrence of
 * the daily publish hour in Europe/Paris, rolling to tomorrow once it passes; pass
 * `target` for a fixed one-shot deadline instead.
 */

export interface CountdownProps {
  /** Fixed deadline. When omitted, counts to the next `hour`:00 in Europe/Paris. */
  target?: Date;
  /** Daily publish hour (0–23) in Europe/Paris, used when `target` is omitted. Defaults to 10. */
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

/** Milliseconds to add to a UTC instant to get the Europe/Paris wall clock. */
function parisOffsetMs(at: Date): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Paris',
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const parts: Record<string, number> = {};
  for (const p of dtf.formatToParts(at)) {
    if (p.type !== 'literal') parts[p.type] = Number(p.value);
  }
  const asUtc = Date.UTC(
    parts.year as number,
    (parts.month as number) - 1,
    parts.day as number,
    parts.hour as number,
    parts.minute as number,
    parts.second as number,
  );
  return asUtc - at.getTime();
}

/**
 * The UTC instant at which the Paris wall clock next reads `hour`:00:00.
 *
 * The bloom happens at 10:00 Paris for everyone on Earth, so this must not use the
 * viewer's own timezone: `setHours` would make a visitor in Tokyo or New York count
 * to their own 10:00 and be hours out. The offset is resolved twice — once for now,
 * once for the candidate instant — so the countdown stays exact across the March and
 * October DST switches, when the offset on the target day differs from today's.
 */
function nextDailyDeadline(hour: number, now: Date): Date {
  const parisNow = new Date(now.getTime() + parisOffsetMs(now));
  const y = parisNow.getUTCFullYear();
  const m = parisNow.getUTCMonth();
  const d = parisNow.getUTCDate();
  const toUtc = (day: number): Date => {
    const guess = new Date(Date.UTC(y, m, day, hour, 0, 0, 0));
    return new Date(guess.getTime() - parisOffsetMs(guess));
  };
  const todayDeadline = toUtc(d);
  return todayDeadline.getTime() > now.getTime() ? todayDeadline : toUtc(d + 1);
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
    <span className={classes} role="timer" aria-label={`${String(label)} ${display}`}>
      {label}
      <b>{display}</b>
    </span>
  );
}

export default Countdown;
