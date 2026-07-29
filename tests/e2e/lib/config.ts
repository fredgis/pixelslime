/**
 * Shared configuration for the W10 e2e harness.
 *
 * `PRIMARY_BASE` is the canonical backend: `uvicorn app.main:app` with FAKE_BACKEND=1,
 * seeded *only* from contracts/cards, serving the mock-off SPA from frontend/dist.
 *
 * `TODAY_BASE` is the optional supplementary backend (tests/e2e/serve_today.py): the
 * same real app with one extra card dated today, so the reveal ceremony can be
 * exercised. Specs that need it skip cleanly when it is unset.
 */
export const PRIMARY_BASE = (process.env.PRIMARY_BASE ?? 'http://127.0.0.1:8080').replace(/\/$/, '');
export const TODAY_BASE = (process.env.TODAY_BASE ?? '').replace(/\/$/, '');

/** Match W6's screenshot viewport exactly so the two sets are comparable. */
export const VIEWPORT = { width: 1440, height: 960 } as const;

/** The WCAG rule tags W6 audited against, so the two axe runs are comparable. */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/** The three serials the real backend is seeded with, from contracts/cards/*.json. */
export const SEED_SERIALS = { mochibo: 1, thundernub: 900, maxlen: 65535 } as const;
