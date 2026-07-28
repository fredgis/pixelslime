import type { CSSProperties, ReactNode, ReactElement } from 'react';
import { color } from '../tokens';
import { readableText } from '../lib/color';

/**
 * <Ribbon/> — the jaunty, slightly-rotated banner used for "✦ DAY 42 ✦" and status
 * flags. Coral by default with an auto-legible label; the tilt gives it that
 * hand-placed sticker feel from the mockup.
 */

export interface RibbonProps {
  children: ReactNode;
  /** Background colour. Defaults to coral. */
  tone?: string;
  /** Tilt in degrees. Defaults to the mockup's -2°. */
  rotate?: number;
  /** Decorative leading glyph. */
  icon?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function Ribbon({
  children,
  tone = color.coral,
  rotate = -2,
  icon,
  className,
  style,
}: RibbonProps): ReactElement {
  const classes = ['ps-ribbon', className ?? ''].filter(Boolean).join(' ');
  return (
    <span
      className={classes}
      style={{
        background: tone,
        color: readableText(tone, color.ink, color.paper),
        transform: `rotate(${rotate}deg)`,
        ...style,
      }}
    >
      {icon != null ? <span aria-hidden="true">{icon}</span> : null}
      {children}
    </span>
  );
}

export default Ribbon;
