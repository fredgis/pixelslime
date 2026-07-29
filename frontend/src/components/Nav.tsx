/**
 * Top navigation. Keyboard-operable links with visible focus rings (via the design's
 * `.ps-focusable`), an active-route indicator, and the day/night theme toggle.
 */
import type { ReactElement } from 'react';
import { NavLink } from 'react-router-dom';
import { SlimeSprite, tokens } from '@/design';
import { useSettingsStore } from '@/store/settings';
import { toast } from '@/store/toast';

const LINKS: ReadonlyArray<{ to: string; label: string; color: string }> = [
  { to: '/', label: "TODAY", color: tokens.color.bubblegum },
  { to: '/dex', label: 'SLIMEDEX', color: tokens.color.mint },
  { to: '/lab', label: 'PUNI LAB', color: tokens.color.sky },
  { to: '/bank', label: 'SMILE BANK', color: tokens.color.sunbeam },
];

export function Nav(): ReactElement {
  const theme = useSettingsStore((s) => s.theme);
  const toggleTheme = useSettingsStore((s) => s.toggleTheme);

  return (
    <header className="sticky top-0 z-40 border-b-4 border-ink bg-paper shadow-chunk">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <NavLink
          to="/"
          className="ps-focusable flex items-center gap-2 font-pixel text-[13px] text-ink"
          aria-label="PixelSlime home"
        >
          <SlimeSprite baseColor={tokens.color.bubblegum} accessory="flower" face="happy" size={30} bob />
          <span className="hidden sm:inline">PIXELSLIME</span>
        </NavLink>

        <ul className="flex flex-1 flex-wrap items-center justify-center gap-1">
          {LINKS.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.to === '/'}
                className="ps-focusable inline-block rounded-pill px-3 py-1.5 font-stat text-[13px] tracking-[2px] text-ink-soft transition-colors"
                style={({ isActive }) =>
                  isActive
                    ? { background: link.color, color: tokens.color.ink }
                    : undefined
                }
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={() => {
            toggleTheme();
            toast(theme === 'day' ? 'Moonlit Puniverse' : 'Sunny side up', theme === 'day' ? '☾' : '☀');
          }}
          className="ps-focusable rounded-pill border-4 border-ink bg-cream px-3 py-1.5 font-pixel text-[11px] text-ink"
          aria-label={theme === 'day' ? 'Switch to night theme' : 'Switch to day theme'}
        >
          {theme === 'day' ? '☾' : '☀'}
        </button>
      </nav>
    </header>
  );
}

export default Nav;
