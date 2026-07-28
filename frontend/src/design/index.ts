/**
 * PIXELSLIME design system — public surface.
 *
 * W6 imports everything from here, e.g.:
 *   import { SlimeCard, AnimatedTitle, tokens } from '@/design';
 * and once, at the app root:
 *   import '@/design/globals.css';
 */

// Tokens & types
export * from './tokens';
export { default as tokens } from './tokens';
export * from './types';

// Colour helpers
export { shade, luminance, contrastRatio, readableText } from './lib/color';

// Hooks
export { useReducedMotion } from './hooks/useReducedMotion';
export { useTypewriter } from './hooks/useTypewriter';
export { usePointerTilt } from './hooks/usePointerTilt';
export type { PointerTiltOptions } from './hooks/usePointerTilt';
export { useConfetti } from './hooks/useConfetti';
export type {
  ConfettiController,
  ConfettiOrigin,
  UseConfettiOptions,
} from './hooks/useConfetti';

// Components
export { AnimatedTitle } from './components/AnimatedTitle';
export type { AnimatedTitleProps } from './components/AnimatedTitle';
export { SlimeSprite } from './components/SlimeSprite';
export type { SlimeSpriteProps } from './components/SlimeSprite';
export { SlimeCard } from './components/SlimeCard';
export type { SlimeCardProps } from './components/SlimeCard';
export { CardFlip } from './components/CardFlip';
export type { CardFlipProps } from './components/CardFlip';
export { StatBar } from './components/StatBar';
export type { StatBarProps } from './components/StatBar';
export { RarityBadge } from './components/RarityBadge';
export type { RarityBadgeProps } from './components/RarityBadge';
export { TypePill } from './components/TypePill';
export type { TypePillProps } from './components/TypePill';
export { Chip } from './components/Chip';
export type { ChipProps } from './components/Chip';
export { PixelButton } from './components/PixelButton';
export type { PixelButtonProps, PixelButtonVariant } from './components/PixelButton';
export { Ribbon } from './components/Ribbon';
export type { RibbonProps } from './components/Ribbon';
export { Countdown } from './components/Countdown';
export type { CountdownProps } from './components/Countdown';
export { Confetti } from './components/Confetti';
export type { ConfettiHandle, ConfettiProps } from './components/Confetti';
export { HoloCard } from './components/HoloCard';
export type { HoloCardProps } from './components/HoloCard';

// Tailwind preset (also importable directly from './tailwind.preset')
export { pixelslimePreset } from './tailwind.preset';
