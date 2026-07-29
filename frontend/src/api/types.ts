/**
 * Convenience aliases over the auto-generated OpenAPI types (`schema.ts`).
 *
 * WHY: `openapi-typescript` produces a deeply-nested `paths`/`components` tree that
 * is unpleasant to reference inline. These aliases give the rest of the app tidy,
 * contract-bound names. If `contracts/openapi.yaml` changes, `npm run gen:api`
 * regenerates `schema.ts` and any drift surfaces here as a compile error — the
 * contract is enforced by the compiler, not by hope.
 */
import type { components, paths } from './schema';

export type Rarity = components['schemas']['Rarity'];
export type SlimeType = components['schemas']['SlimeType'];
export type ApiError = components['schemas']['Error'];
export type CardSummary = components['schemas']['CardSummary'];
export type Card = components['schemas']['Card'];

/** Response of `GET /api/cards/today`. */
export type TodayResponse =
  paths['/api/cards/today']['get']['responses']['200']['content']['application/json'];

/** Response of `GET /api/cards` (a page of summaries). */
export type CardsPage =
  paths['/api/cards']['get']['responses']['200']['content']['application/json'];

/** Query parameters accepted by `GET /api/cards`. */
export type CardsQuery = NonNullable<paths['/api/cards']['get']['parameters']['query']>;

export type CardsSort = NonNullable<CardsQuery['sort']>;

/** Response of `GET /api/cards/{serial}/raw` — the provenance view. */
export type RawResponse =
  paths['/api/cards/{serial}/raw']['get']['responses']['200']['content']['application/json'];

/** One verbatim asmDB row inside {@link RawResponse}. */
export type RawRow = RawResponse['rows'][number];

/** Response of `GET /api/stats`. */
export type StatsResponse =
  paths['/api/stats']['get']['responses']['200']['content']['application/json'];

/** Response of `GET /api/health`. */
export type HealthResponse =
  paths['/api/health']['get']['responses']['200']['content']['application/json'];

/** Response of `GET /api/nft/{serial}` — ERC-721 metadata. */
export type NftMetadata =
  paths['/api/nft/{serial}']['get']['responses']['200']['content']['application/json'];

/** The chain anchor sub-object on a {@link Card}, when minted. */
export type ChainAnchor = NonNullable<Card['chain']>;
