/**
 * The typed API client and its TanStack Query hooks.
 *
 * Every function here speaks the `contracts/openapi.yaml` surface through the
 * generated types, so a contract change becomes a compile error rather than a
 * runtime surprise. The same code path serves the MSW mock and the real backend —
 * only `lib/config` decides where the requests actually land.
 */
import {
  useQuery,
  keepPreviousData,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiUrl } from '@/lib/config';
import type {
  Card,
  CardsPage,
  CardsQuery,
  HealthResponse,
  NftMetadata,
  RawResponse,
  StatsResponse,
  TodayResponse,
} from './types';

/** Raised when the API answers with a non-2xx status. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    headers: { Accept: 'application/json' },
    ...init,
  });

  if (!response.ok) {
    let code = 'http_error';
    let message = `Request to ${path} failed with ${response.status}`;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === 'object' &&
        body !== null &&
        'error' in body &&
        typeof (body as { error: unknown }).error === 'object'
      ) {
        const err = (body as { error: { code?: string; message?: string } }).error;
        code = err.code ?? code;
        message = err.message ?? message;
      }
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiRequestError(response.status, code, message);
  }

  return (await response.json()) as T;
}

/** Serialise the SLIMEDEX query into a stable, contract-shaped search string. */
export function buildCardsSearch(query: CardsQuery): string {
  const params = new URLSearchParams();
  if (query.page) params.set('page', String(query.page));
  if (query.size) params.set('size', String(query.size));
  if (query.type) params.set('type', query.type);
  if (query.rarity) params.set('rarity', query.rarity);
  if (query.sort) params.set('sort', query.sort);
  if (query.q && query.q.trim()) params.set('q', query.q.trim());
  const search = params.toString();
  return search ? `?${search}` : '';
}

export const queryKeys = {
  health: ['health'] as const,
  today: ['cards', 'today'] as const,
  cards: (query: CardsQuery) => ['cards', 'list', query] as const,
  card: (serial: number) => ['cards', 'detail', serial] as const,
  raw: (serial: number) => ['cards', 'raw', serial] as const,
  stats: ['stats'] as const,
  nft: (serial: number) => ['nft', serial] as const,
};

export function useHealth(): UseQueryResult<HealthResponse, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => request<HealthResponse>('/api/health'),
    staleTime: 60_000,
  });
}

export function useToday(): UseQueryResult<TodayResponse, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.today,
    queryFn: () => request<TodayResponse>('/api/cards/today'),
    staleTime: 60_000,
  });
}

export function useCards(query: CardsQuery): UseQueryResult<CardsPage, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.cards(query),
    queryFn: () => request<CardsPage>(`/api/cards${buildCardsSearch(query)}`),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useCard(
  serial: number | undefined,
): UseQueryResult<Card, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.card(serial ?? -1),
    queryFn: () => request<Card>(`/api/cards/${serial ?? -1}`),
    enabled: serial !== undefined && Number.isFinite(serial),
  });
}

export function useRawCard(
  serial: number | undefined,
): UseQueryResult<RawResponse, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.raw(serial ?? -1),
    queryFn: () => request<RawResponse>(`/api/cards/${serial ?? -1}/raw`),
    enabled: serial !== undefined && Number.isFinite(serial),
  });
}

export function useStats(): UseQueryResult<StatsResponse, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.stats,
    queryFn: () => request<StatsResponse>('/api/stats'),
    staleTime: 60_000,
  });
}

export function useNft(
  serial: number | undefined,
): UseQueryResult<NftMetadata, ApiRequestError> {
  return useQuery({
    queryKey: queryKeys.nft(serial ?? -1),
    queryFn: () => request<NftMetadata>(`/api/nft/${serial ?? -1}`),
    enabled: serial !== undefined && Number.isFinite(serial),
  });
}
