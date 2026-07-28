import type { ButtonHTMLAttributes, ReactNode, ReactElement } from 'react';
import { color } from '../tokens';
import { readableText } from '../lib/color';

/**
 * <PixelButton/> — the chunky arcade button with the signature `0 6px 0` press-down
 * shadow: it lifts on hover and physically presses on click. It is a real <button>,
 * so keyboard activation and focus come for free; the aesthetic focus ring lives in
 * globals.css. Icon-only buttons must pass `aria-label`.
 */

export type PixelButtonVariant = 'sunbeam' | 'pink' | 'mint' | 'ghost' | 'coral';

export interface PixelButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: PixelButtonVariant;
  size?: 'sm' | 'md';
  /** Leading glyph/emoji; decorative (hidden from assistive tech). */
  iconLeft?: ReactNode;
  /** Stretch to fill the container width. */
  block?: boolean;
}

const VARIANT_BG: Record<PixelButtonVariant, string> = {
  sunbeam: color.sunbeam,
  pink: color.bubblegum,
  mint: color.mint,
  ghost: color.paper,
  coral: color.coral,
};

export function PixelButton({
  variant = 'sunbeam',
  size = 'md',
  iconLeft,
  block = false,
  children,
  className,
  type = 'button',
  style,
  ...rest
}: PixelButtonProps): ReactElement {
  const bg = VARIANT_BG[variant];
  const classes = [
    'ps-btn',
    size === 'sm' ? 'ps-btn--sm' : '',
    block ? 'ps-btn--block' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    // eslint-disable-next-line react/button-has-type -- `type` is defaulted above
    <button
      className={classes}
      style={{ background: bg, color: readableText(bg, color.ink, color.paper), ...style }}
      type={type}
      {...rest}
    >
      {iconLeft != null ? <span aria-hidden="true">{iconLeft}</span> : null}
      {children}
    </button>
  );
}

export default PixelButton;
