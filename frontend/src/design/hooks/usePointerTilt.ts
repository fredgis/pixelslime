import { useEffect, useRef } from 'react';

export interface PointerTiltOptions {
  /** Maximum tilt in degrees toward the pointer on each axis. */
  maxTilt?: number;
  /** Scale applied while the pointer (or device) is engaged. */
  scale?: number;
  /** Upward lift in px while engaged — the gallery tile's hover pop. */
  liftY?: number;
  /** A flat z-rotation in degrees while engaged — the tile's playful skew. */
  baseRotate?: number;
  /** Perspective in px baked into the transform. */
  perspective?: number;
  /** Also expose pointer position as `--ps-glare-x/y` for a holographic glare. */
  glare?: boolean;
  /** Class toggled on the element while engaged (e.g. to reveal a glare layer). */
  activeClass?: string;
  /** Respond to device orientation too (mobile gyroscope), for the detail view. */
  gyroscope?: boolean;
  /** False disables all listeners and holds the element flat (reduced motion). */
  enabled?: boolean;
}

/**
 * Ref-based 3D tilt, shared by <SlimeCard/> (hover lift + tilt) and <HoloCard/>
 * (pointer/gyroscope holographic tilt). It writes transforms straight to the DOM
 * node — no React re-render per pointer event, so it stays 60fps. When disabled
 * it attaches nothing and the element rests flat, which is the reduced-motion
 * degrade required by the brief.
 */
export function usePointerTilt<T extends HTMLElement>(
  options: PointerTiltOptions = {},
): React.RefObject<T> {
  const {
    maxTilt = 14,
    scale = 1.03,
    liftY = 0,
    baseRotate = 0,
    perspective = 900,
    glare = false,
    activeClass,
    gyroscope = false,
    enabled = true,
  } = options;

  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || !enabled) return;

    const apply = (tiltX: number, tiltY: number): void => {
      node.style.transform =
        `perspective(${perspective}px) translateY(${liftY}px) ` +
        `rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg) ` +
        `rotate(${baseRotate}deg) scale(${scale})`;
    };
    const reset = (): void => {
      node.style.transform = '';
      if (activeClass) node.classList.remove(activeClass);
    };

    const onPointerMove = (event: PointerEvent): void => {
      const rect = node.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width - 0.5;
      const py = (event.clientY - rect.top) / rect.height - 0.5;
      apply(py * -maxTilt, px * maxTilt);
      if (activeClass) node.classList.add(activeClass);
      if (glare) {
        node.style.setProperty('--ps-glare-x', `${(px + 0.5) * 100}%`);
        node.style.setProperty('--ps-glare-y', `${(py + 0.5) * 100}%`);
      }
    };

    const onOrientation = (event: DeviceOrientationEvent): void => {
      if (event.beta === null || event.gamma === null) return;
      const clamp = (v: number): number => Math.max(-1, Math.min(1, v));
      apply(clamp(event.beta / 45) * -maxTilt, clamp(event.gamma / 45) * maxTilt);
      if (activeClass) node.classList.add(activeClass);
    };

    node.addEventListener('pointermove', onPointerMove);
    node.addEventListener('pointerleave', reset);
    if (gyroscope && typeof window !== 'undefined') {
      window.addEventListener('deviceorientation', onOrientation);
    }

    return () => {
      node.removeEventListener('pointermove', onPointerMove);
      node.removeEventListener('pointerleave', reset);
      if (gyroscope && typeof window !== 'undefined') {
        window.removeEventListener('deviceorientation', onOrientation);
      }
      reset();
    };
  }, [maxTilt, scale, liftY, baseRotate, perspective, glare, activeClass, gyroscope, enabled]);

  return ref;
}
