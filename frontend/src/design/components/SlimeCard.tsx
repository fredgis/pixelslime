import { useEffect, useState } from 'react';
import type { CSSProperties, ReactElement } from 'react';
import { RARITY_ORDER, toCardId } from '../types';
import type { SlimeCardData } from '../types';
import { rarity, typeColor } from '../tokens';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { usePointerTilt } from '../hooks/usePointerTilt';
import { SlimeSprite } from './SlimeSprite';

/**
 * <SlimeCard/> — a SLIMEDEX gallery tile. It shows real artwork when available and
 * falls back to the procedural sprite otherwise — including when the image URL fails
 * to load (onError), so a dead blob degrades to a cute slime rather than a blank
 * hole. `locked` renders the Pokédex-style dark "? ? ? ? ?" silhouette and hides
 * every tier tell — name, type, the rarity house tag and even the holo intensity —
 * so a silhouette never spoils what is waiting inside. On hover it lifts and tilts
 * toward the pointer, and a holographic sheen sweeps across it whose strength scales
 * with rarity (revealed cards only). It is a real <button>, so it is fully keyboard-
 * operable, and the reduced-motion degrade (no tilt, quiet fade-in) is honoured.
 */

export interface SlimeCardProps {
  card: SlimeCardData;
  /** Render the unrevealed silhouette. */
  locked?: boolean;
  /** Show the bouncing NEW! flag. */
  isNew?: boolean;
  onOpen?: (serial: number) => void;
  /** Position in the grid, used to stagger the entrance. */
  index?: number;
  className?: string;
}

export function SlimeCard({
  card,
  locked = false,
  isNew = false,
  onOpen,
  index = 0,
  className,
}: SlimeCardProps): ReactElement {
  const reduced = useReducedMotion();
  const ref = usePointerTilt<HTMLButtonElement>({
    maxTilt: 10,
    liftY: -10,
    baseRotate: -1.2,
    scale: 1.03,
    perspective: 700,
    enabled: !reduced,
  });

  // Fall back to the procedural sprite if the artwork 404s / fails to decode.
  const [imgError, setImgError] = useState(false);
  useEffect(() => {
    setImgError(false);
  }, [card.imageSrc]);

  const info = rarity[card.rarity];
  const cardId = card.cardId ?? toCardId(card.serial);
  // A locked tile must not leak its tier, so its holo sheen uses a fixed neutral
  // intensity rather than the rarity-scaled one.
  const holoStrength = locked ? 0.3 : 0.35 + RARITY_ORDER.indexOf(card.rarity) * 0.13;
  const showImage = Boolean(card.imageSrc) && !locked && !imgError;

  const label = locked
    ? `Unrevealed slime ${cardId}`
    : `${cardId} ${card.name}, ${card.rarity} ${info.house}, ${card.type} type`;

  const style: CSSProperties = {
    ['--ps-holo-strength' as string]: holoStrength,
    ...(reduced ? {} : { animation: `ps-bobin .6s var(--ps-pop) ${Math.min(index, 8) * 40}ms backwards` }),
  };

  const classes = [
    'ps-tile',
    'ps-animate-in',
    locked ? 'locked' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      ref={ref}
      type="button"
      className={classes}
      style={style}
      aria-label={label}
      onClick={() => onOpen?.(card.serial)}
    >
      <span className="ps-tile__serial">{cardId}</span>
      {isNew ? <span className="ps-newbadge">NEW!</span> : null}

      <div className="ps-tile__art">
        {showImage ? (
          <img
            src={card.imageSrc}
            alt=""
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <SlimeSprite
            baseColor={card.spriteColor}
            accessory={card.accessory}
            face={card.face}
          />
        )}
        <span className="ps-holo" />
      </div>

      <div className="ps-tile__meta">
        <div className="ps-tile__name">{locked ? '? ? ? ? ?' : card.name}</div>
        <div className="ps-tile__row">
          {locked ? (
            <span className="ps-tile__locktag">◆ UNDISCOVERED ◆</span>
          ) : (
            <>
              <span style={{ color: typeColor[card.type], fontWeight: 700 }}>
                {card.type}
              </span>
              <span className="ps-tile__rartag" style={{ background: info.color }}>
                {info.house.toUpperCase()}
              </span>
            </>
          )}
        </div>
      </div>
    </button>
  );
}

export default SlimeCard;
