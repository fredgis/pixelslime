/**
 * App chrome shared by every route: the themed `.ps-surface`, the ambient drifting
 * slimes, the top nav, a routed <Outlet/>, the footer walker, and the toast layer.
 * The theme class is applied to <html> so the design system's CSS vars flip globally.
 */
import { useEffect, type ReactElement } from 'react';
import { Outlet } from 'react-router-dom';
import { SlimeSprite, tokens } from '@/design';
import { useSettingsStore } from '@/store/settings';
import { useAmbientStore } from '@/store/ambient';
import Nav from './Nav';
import BackgroundSlimes from './BackgroundSlimes';
import Toaster from './Toaster';

export function Layout(): ReactElement {
  const theme = useSettingsStore((s) => s.theme);
  const tint = useAmbientStore((s) => s.tint);

  useEffect(() => {
    document.documentElement.dataset.theme = theme === 'night' ? 'night' : '';
  }, [theme]);

  return (
    <div className="ps-surface min-h-screen">
      <a
        href="#main"
        className="ps-focusable sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-pill focus:border-4 focus:border-ink focus:bg-sunbeam focus:px-4 focus:py-2 focus:font-pixel focus:text-[11px] focus:text-ink"
      >
        Skip to content
      </a>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 transition-opacity duration-slow"
        style={{ background: tint ?? 'transparent', opacity: tint ? 1 : 0 }}
      />
      <BackgroundSlimes />
      <div className="relative z-10 flex min-h-screen flex-col">
        <Nav />
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          <Outlet />
        </main>
        <footer className="relative z-10 border-t-4 border-ink bg-paper">
          <div className="mx-auto flex max-w-6xl flex-col items-center gap-2 px-4 py-6 text-center">
            <SlimeSprite baseColor={tokens.color.mint} accessory="leaf" face="happy" size={40} bob />
            <p className="font-stat text-[12px] tracking-[3px] text-ink-soft">
              PIXELSLIME · PUNIPUNI PARADISE · a slime a day, forever
            </p>
            <p className="font-stat text-[11px] tracking-[2px] text-ink-soft">
              175 bytes of pure joy · anchored on Polygon Amoy
            </p>
          </div>
        </footer>
      </div>
      <Toaster />
    </div>
  );
}

export default Layout;
