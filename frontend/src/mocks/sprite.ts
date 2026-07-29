/**
 * Procedural slime-sprite SVG string generator for the mock's image endpoints.
 *
 * The design system ships <SlimeSprite/> as a React component, but the mock needs a
 * plain SVG *string* to hand back from `/api/cards/{serial}/thumb|image` and to bake
 * into `data:` thumbnail URIs for cards that have no real artwork. This is a faithful
 * port of `slimeSVG` from docs/mockup/index.html — the same 16×12 grid, the same
 * `shade()` maths — wrapped in a 3:4 card frame with a soft rarity-tinted background
 * so procedural tiles read as real cards. Mock-only; never in the app bundle.
 */
import { z85Encode } from './psc';

export type MockAccessory = 'flower' | 'leaf' | 'star' | 'horn' | 'none';
export type MockFace = 'happy' | 'smug' | 'sleepy';

const BODY: ReadonlyArray<readonly [number, number]> = [
  [5, 10], [3, 12], [2, 13], [1, 14], [1, 14], [0, 15],
  [0, 15], [0, 15], [0, 15], [0, 15], [0, 15], [0, 15],
];

const ACCESSORIES: Record<MockAccessory, ReadonlyArray<readonly [number, number, string]>> = {
  flower: [
    [6, 0, '#FFF3F7'], [7, 0, '#FFF3F7'], [5, 1, '#FFF3F7'], [8, 1, '#FFF3F7'],
    [6, 1, '#FFD86B'], [7, 1, '#FFD86B'], [9, 1, '#7FE3C0'], [10, 2, '#7FE3C0'],
  ],
  leaf: [[7, 0, '#6BC98A'], [8, 0, '#6BC98A'], [8, 1, '#4FA96C'], [9, 1, '#6BC98A']],
  star: [[7, 0, '#FFD86B'], [6, 1, '#FFD86B'], [7, 1, '#FFF0B8'], [8, 1, '#FFD86B']],
  horn: [[6, 0, '#FFFFFF'], [7, 0, '#E7DCFF'], [6, 1, '#E7DCFF'], [7, 1, '#FFFFFF']],
  none: [],
};

function shade(hex: string, amt: number): string {
  const n = parseInt(hex.slice(1), 16);
  const c = (v: number): number => Math.max(0, Math.min(255, v));
  return (
    '#' +
    ((c((n >> 16) + amt) << 16) | (c(((n >> 8) & 255) + amt) << 8) | c((n & 255) + amt))
      .toString(16)
      .padStart(6, '0')
  );
}

/** Build the raw 16×12 sprite `<rect>` markup for a slime. */
function spriteRects(base: string, accessory: MockAccessory, face: MockFace): string {
  const light = shade(base, 52);
  const dark = shade(base, -46);
  const px: string[] = [];
  const R = (x: number, y: number, f: string, o = 1): void => {
    px.push(`<rect x="${x}" y="${y}" width="1" height="1" fill="${f}"${o < 1 ? ` opacity="${o}"` : ''}/>`);
  };

  BODY.forEach(([a, b], y) => {
    for (let x = a; x <= b; x += 1) R(x, y, base);
  });
  [[4, 1], [5, 1], [4, 2], [5, 2], [6, 2], [3, 3], [4, 3], [5, 3]].forEach(([x, y]) => R(x, y, light));
  for (let x = 0; x <= 15; x += 1) R(x, 11, dark);
  for (let x = 1; x <= 14; x += 1) R(x, 10, dark, 0.42);

  const EY = 5;
  [4, 10].forEach((ex) => {
    for (let y = EY; y < EY + 3; y += 1) {
      R(ex, y, '#2B1B4A');
      R(ex + 1, y, '#2B1B4A');
    }
    R(ex, EY, '#FFFFFF');
  });
  [[2, 7], [3, 7], [12, 7], [13, 7]].forEach(([x, y]) => R(x, y, '#FF8FC5', 0.85));

  if (face === 'happy') {
    R(7, 8, '#2B1B4A'); R(8, 8, '#2B1B4A'); R(7, 9, '#FF6FA5'); R(8, 9, '#FF6FA5');
  } else if (face === 'smug') {
    R(6, 8, '#2B1B4A'); R(7, 9, '#2B1B4A'); R(8, 9, '#2B1B4A'); R(9, 8, '#2B1B4A');
  } else {
    R(7, 8, '#2B1B4A'); R(8, 8, '#2B1B4A');
  }
  ACCESSORIES[accessory].forEach(([x, y, f]) => R(x, y, f));
  return px.join('');
}

export interface MockArtOptions {
  baseColor: string;
  accessory: MockAccessory;
  face: MockFace;
  /** Rarity tint for the card background halo. */
  rarityColor: string;
}

/**
 * A full 3:4 "card" SVG: a rounded rarity-tinted panel with the slime centred, sized
 * to sit edge-to-edge inside a gallery tile's `object-fit: contain` art box.
 */
export function mockCardSvg({ baseColor, accessory, face, rarityColor }: MockArtOptions): string {
  const rects = spriteRects(baseColor, accessory, face);
  const top = shade(baseColor, 40);
  const bottom = shade(baseColor, -24);
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 320" width="240" height="320">` +
    `<defs>` +
    `<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/>` +
    `</linearGradient>` +
    `<radialGradient id="halo" cx="50%" cy="42%" r="60%">` +
    `<stop offset="0" stop-color="${rarityColor}" stop-opacity="0.55"/>` +
    `<stop offset="0.66" stop-color="${rarityColor}" stop-opacity="0"/>` +
    `</radialGradient>` +
    `</defs>` +
    `<rect width="240" height="320" rx="18" fill="url(#bg)"/>` +
    `<rect width="240" height="320" rx="18" fill="url(#halo)"/>` +
    `<g transform="translate(48 76) scale(9)" shape-rendering="crispEdges">${rects}</g>` +
    `</svg>`
  );
}

/** A bare, transparent sprite SVG (used where the design would draw <SlimeSprite/>). */
export function mockSpriteSvg(baseColor: string, accessory: MockAccessory, face: MockFace): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 12" shape-rendering="crispEdges">` +
    `${spriteRects(baseColor, accessory, face)}</svg>`
  );
}

/** Encode an SVG string as a compact `data:` URI usable directly in `<img src>`. */
export function svgDataUri(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

/**
 * A deterministic "art hash" for procedural cards, so the provenance stream folds in
 * something derived from the picture — mirroring the real pipeline's `art_sha`.
 */
export function pseudoArtId(seed: number): string {
  const bytes = new Uint8Array(4);
  let x = (seed * 2654435761) % 4294967296;
  for (let i = 0; i < 4; i += 1) {
    x = (x * 1103515245 + 12345) % 2147483648;
    bytes[i] = x % 256;
  }
  return z85Encode(bytes);
}
