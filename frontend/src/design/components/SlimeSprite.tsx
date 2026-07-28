import { useMemo } from 'react';
import type { CSSProperties, ReactElement } from 'react';
import { sprite } from '../tokens';
import type { SlimeAccessory, SlimeFace } from '../types';
import { shade } from '../lib/color';

/**
 * <SlimeSprite/> — the procedural pixel-art slime.
 *
 * A faithful port of `slimeSVG` from docs/mockup/index.html: a 16×12 grid of 1×1
 * <rect>s with `shape-rendering="crispEdges"`, deterministic from its props. The
 * body is `baseColor`; light and shadow are derived from it with the same `shade`
 * maths as the mockup, so the sprite is fully driven by one colour plus a choice
 * of accessory and face. Every fixed hue comes from tokens.sprite — no literals.
 */

export interface SlimeSpriteProps {
  /** Body colour. Light/shadow variants are derived from it. */
  baseColor?: string;
  accessory?: SlimeAccessory;
  face?: SlimeFace;
  /** Rendered width in px. Height follows the 16×12 aspect. */
  size?: number;
  /** Apply the gentle idle bob animation. */
  bob?: boolean;
  /** Accessible name. When set the sprite is a labelled image; otherwise decorative. */
  title?: string;
  className?: string;
  style?: CSSProperties;
}

/** Body span [xStart, xEnd] (inclusive) per row y = 0..11. */
const BODY: ReadonlyArray<readonly [number, number]> = [
  [5, 10],
  [3, 12],
  [2, 13],
  [1, 14],
  [1, 14],
  [0, 15],
  [0, 15],
  [0, 15],
  [0, 15],
  [0, 15],
  [0, 15],
  [0, 15],
];

const SHINE: ReadonlyArray<readonly [number, number]> = [
  [4, 1],
  [5, 1],
  [4, 2],
  [5, 2],
  [6, 2],
  [3, 3],
  [4, 3],
  [5, 3],
];

const BLUSH: ReadonlyArray<readonly [number, number]> = [
  [2, 7],
  [3, 7],
  [12, 7],
  [13, 7],
];

const { accessory: acc } = sprite;

/** Accessory pixels [x, y, colour] — colours sourced from tokens.sprite. */
const ACCESSORIES: Record<SlimeAccessory, ReadonlyArray<readonly [number, number, string]>> = {
  flower: [
    [6, 0, acc.flowerPetal],
    [7, 0, acc.flowerPetal],
    [5, 1, acc.flowerPetal],
    [8, 1, acc.flowerPetal],
    [6, 1, acc.flowerCore],
    [7, 1, acc.flowerCore],
    [9, 1, acc.flowerLeaf],
    [10, 2, acc.flowerLeaf],
  ],
  leaf: [
    [7, 0, acc.leaf],
    [8, 0, acc.leaf],
    [8, 1, acc.leafDark],
    [9, 1, acc.leaf],
  ],
  star: [
    [7, 0, acc.star],
    [6, 1, acc.star],
    [7, 1, acc.starShine],
    [8, 1, acc.star],
  ],
  horn: [
    [6, 0, acc.hornLight],
    [7, 0, acc.hornDark],
    [6, 1, acc.hornDark],
    [7, 1, acc.hornLight],
  ],
  none: [],
};

function buildRects(baseColor: string, accessory: SlimeAccessory, face: SlimeFace): ReactElement[] {
  const light = shade(baseColor, 52);
  const dark = shade(baseColor, -46);
  const rects: ReactElement[] = [];
  let k = 0;
  const push = (x: number, y: number, fill: string, opacity = 1): void => {
    rects.push(
      <rect
        key={k++}
        x={x}
        y={y}
        width={1}
        height={1}
        fill={fill}
        {...(opacity < 1 ? { opacity } : {})}
      />,
    );
  };

  BODY.forEach(([a, b], y) => {
    for (let x = a; x <= b; x += 1) push(x, y, baseColor);
  });
  SHINE.forEach(([x, y]) => push(x, y, light));
  for (let x = 0; x <= 15; x += 1) push(x, 11, dark);
  for (let x = 1; x <= 14; x += 1) push(x, 10, dark, 0.42);

  const EY = 5;
  [4, 10].forEach((ex) => {
    for (let y = EY; y < EY + 3; y += 1) {
      push(ex, y, sprite.eye);
      push(ex + 1, y, sprite.eye);
    }
    push(ex, EY, sprite.eyeShine);
  });

  BLUSH.forEach(([x, y]) => push(x, y, sprite.blush, 0.85));

  if (face === 'happy') {
    push(7, 8, sprite.mouthDark);
    push(8, 8, sprite.mouthDark);
    push(7, 9, sprite.mouthPink);
    push(8, 9, sprite.mouthPink);
  } else if (face === 'smug') {
    push(6, 8, sprite.mouthDark);
    push(7, 9, sprite.mouthDark);
    push(8, 9, sprite.mouthDark);
    push(9, 8, sprite.mouthDark);
  } else {
    push(7, 8, sprite.mouthDark);
    push(8, 8, sprite.mouthDark);
  }

  ACCESSORIES[accessory].forEach(([x, y, fill]) => push(x, y, fill));
  return rects;
}

export function SlimeSprite({
  baseColor = '#FF9EC4',
  accessory = 'none',
  face = 'happy',
  size,
  bob = false,
  title,
  className,
  style,
}: SlimeSpriteProps): ReactElement {
  const rects = useMemo(
    () => buildRects(baseColor, accessory, face),
    [baseColor, accessory, face],
  );
  const classes = ['ps-sprite', bob ? 'ps-sprite--bob' : '', className ?? '']
    .filter(Boolean)
    .join(' ');

  return (
    <svg
      viewBox="0 0 16 12"
      {...(size ? { width: size } : {})}
      shapeRendering="crispEdges"
      xmlns="http://www.w3.org/2000/svg"
      className={classes}
      style={style}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      {rects}
    </svg>
  );
}

export default SlimeSprite;
