/**
 * Colour helpers. Ported from the `shade()` used throughout docs/mockup/index.html
 * so procedural sprites and stat bars derive their light/dark variants exactly the
 * way the approved mockup does — no new hand-picked hexes required.
 */

/** Clamp a channel to the 0–255 byte range. */
function clampByte(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}

/**
 * Lighten (positive `amt`) or darken (negative `amt`) a `#rrggbb` hex by shifting
 * every channel by `amt`. This is the mockup's algorithm verbatim.
 */
export function shade(hex: string, amt: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = clampByte((n >> 16) + amt);
  const g = clampByte(((n >> 8) & 255) + amt);
  const b = clampByte((n & 255) + amt);
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
}

/** Linearise one 0–255 sRGB channel per the WCAG definition. */
function linearChannel(byte: number): number {
  const c = byte / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance (0–1). */
export function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * linearChannel(n >> 16) +
    0.7152 * linearChannel((n >> 8) & 255) +
    0.0722 * linearChannel(n & 255)
  );
}

/** WCAG contrast ratio between two hex colours (1–21). */
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Choose whichever of two candidate ink colours (typically dark ink vs near-white
 * paper) has the HIGHER contrast against `bgHex`. Picking the maximum available
 * contrast is the strongest guarantee a two-colour text system can give, so every
 * coloured pill/badge stays as legible as possible — unlike the mockup's fixed
 * white, which fails AA on the bright pinks.
 */
export function readableText(bgHex: string, inkHex: string, paperHex: string): string {
  return contrastRatio(bgHex, inkHex) >= contrastRatio(bgHex, paperHex) ? inkHex : paperHex;
}
