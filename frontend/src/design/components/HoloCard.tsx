import type { ReactNode, ReactElement } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { usePointerTilt } from '../hooks/usePointerTilt';

/**
 * <HoloCard/> — the pointer/gyroscope-driven holographic tilt for the SLIME PROFILE.
 * The card leans toward the cursor (or the phone's tilt) and a soft glare tracks the
 * pointer across a foil sheen. Purely presentational, so there is no keyboard trap;
 * under reduced motion it holds perfectly flat.
 */

export interface HoloCardProps {
  /** Card content. Ignored when `imageSrc` is provided. */
  children?: ReactNode;
  imageSrc?: string;
  imageAlt?: string;
  /** Maximum tilt in degrees. Defaults to 14. */
  maxTilt?: number;
  /** React to device orientation on mobile. Defaults to true. */
  gyroscope?: boolean;
  /** Show the tracking glare. Defaults to true. */
  glare?: boolean;
  className?: string;
}

export function HoloCard({
  children,
  imageSrc,
  imageAlt = '',
  maxTilt = 14,
  gyroscope = true,
  glare = true,
  className,
}: HoloCardProps): ReactElement {
  const reduced = useReducedMotion();
  const ref = usePointerTilt<HTMLDivElement>({
    maxTilt,
    scale: 1.03,
    perspective: 900,
    glare,
    gyroscope,
    activeClass: 'ps-holocard--active',
    enabled: !reduced,
  });

  const classes = ['ps-holocard', className ?? ''].filter(Boolean).join(' ');

  return (
    <div ref={ref} className={classes}>
      {imageSrc ? <img src={imageSrc} alt={imageAlt} /> : children}
      {glare ? <span className="ps-holocard__glare" aria-hidden="true" /> : null}
    </div>
  );
}

export default HoloCard;
