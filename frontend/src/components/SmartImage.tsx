/**
 * Lazy, responsive `<img>` with an automatic 512w/1024w srcset.
 *
 * The design system's SlimeCard/CardFlip/HoloCard each render a single `<img>`, so the
 * two biggest images (today's flip face and the profile hero) get srcset by passing a
 * SmartImage as their `children` instead of an `imageSrc`. When `thumb` equals `src`
 * (procedural data-URIs), no srcset is emitted.
 */
import type { ReactElement } from 'react';

export interface SmartImageProps {
  src: string;
  /** The 512w variant, if distinct from `src`. */
  thumb?: string;
  alt: string;
  sizes?: string;
  className?: string;
  width?: number;
  height?: number;
  /** Eager-load above-the-fold heroes; defaults to lazy. */
  eager?: boolean;
}

export function SmartImage({
  src,
  thumb,
  alt,
  sizes = '(max-width: 640px) 90vw, 420px',
  className,
  width,
  height,
  eager = false,
}: SmartImageProps): ReactElement {
  const hasSrcSet = thumb != null && thumb !== src && !src.startsWith('data:');
  return (
    <img
      src={src}
      srcSet={hasSrcSet ? `${thumb} 512w, ${src} 1024w` : undefined}
      sizes={hasSrcSet ? sizes : undefined}
      alt={alt}
      className={className}
      width={width}
      height={height}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
    />
  );
}

export default SmartImage;
