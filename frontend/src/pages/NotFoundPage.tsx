/**
 * `/*` — a friendly 404 that stays in-world.
 */
import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { PixelButton, SlimeSprite, tokens } from '@/design';
import { HeroTitle } from '@/components/HeroTitle';

export function NotFoundPage(): ReactElement {
  return (
    <section className="flex flex-col items-center gap-6 py-16 text-center">
      <SlimeSprite baseColor={tokens.color.grape} accessory="horn" face="sleepy" size={120} bob />
      <HeroTitle text="LOST?" eyebrow="404" subtitle="THIS SLIME WANDERED OFF" typewriter={false} />
      <Link to="/">
        <PixelButton variant="pink">Back to today’s bloom</PixelButton>
      </Link>
    </section>
  );
}

export default NotFoundPage;
