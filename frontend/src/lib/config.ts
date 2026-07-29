/**
 * Runtime configuration, driven entirely by Vite env vars so a single flag flips
 * the whole app between the MSW mock and the real W7 backend.
 *
 * - `VITE_USE_MOCK=true`  → the app boots the Mock Service Worker and every request
 *   is answered locally from seed data generated off `contracts/openapi.yaml`.
 * - `VITE_USE_MOCK=false` → requests go to `VITE_API_BASE` (default: same origin),
 *   which is exactly what W7 serves the built `dist/` behind.
 *
 * Default: mock ON in `dev`, OFF in a production build, unless explicitly overridden.
 * This keeps `npm run dev` self-contained while letting W7 serve a real-API build.
 */

function readFlag(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined || value === '') return fallback;
  return value === 'true' || value === '1';
}

/**
 * Whether the Mock Service Worker should intercept API calls.
 *
 * NOTE: the dynamic `import('./mocks/browser')` in main.tsx inlines this same
 * `import.meta.env` expression directly so Rollup can statically drop the mock
 * chunk from a plain production build (real-API build for W7). Keep them in sync.
 */
export const USE_MOCK: boolean = readFlag(import.meta.env.VITE_USE_MOCK, import.meta.env.DEV);

/** Base URL for the real API. Empty string means same-origin (`/api/...`). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

/** Prefix a contract path with the configured API base. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
