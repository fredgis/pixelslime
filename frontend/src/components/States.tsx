/**
 * Friendly loading / error / empty states, in-character with the pixel world.
 */
import type { ReactElement } from 'react';
import { PixelButton, SlimeSprite, tokens } from '@/design';

export function LoadingState({ label = 'Blooming…' }: { label?: string }): ReactElement {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-ink-soft" role="status" aria-live="polite">
      <SlimeSprite baseColor={tokens.color.mint} face="sleepy" size={88} bob />
      <p className="font-stat tracking-[4px]">{label}</p>
    </div>
  );
}

export function ErrorState({
  label = 'This slime wandered off.',
  onRetry,
}: {
  label?: string;
  onRetry?: () => void;
}): ReactElement {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center" role="alert">
      <SlimeSprite baseColor={tokens.color.coral} face="smug" size={88} />
      <p className="font-pixel text-[12px] text-ink">{label}</p>
      {onRetry ? (
        <PixelButton variant="mint" onClick={onRetry}>
          Try again
        </PixelButton>
      ) : null}
    </div>
  );
}

export function EmptyState({ label = 'No slimes match — yet.' }: { label?: string }): ReactElement {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center text-ink-soft">
      <SlimeSprite baseColor={tokens.color.sky} face="happy" size={80} />
      <p className="font-stat tracking-[3px]">{label}</p>
    </div>
  );
}
