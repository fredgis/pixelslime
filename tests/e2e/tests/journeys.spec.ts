/**
 * User journeys against the REAL backend. Each journey ties something the UI shows back
 * to what the real API actually returned, and captures a screenshot named to mirror W6's
 * mock-driven set (frontend/screenshots/*) so the two can be compared directly.
 *
 * The real backend is seeded from only the three contracts/cards (serials 1, 900, 65535),
 * so several screens necessarily differ from W6's 14-card mock. Where that happens the
 * test asserts the *shape/behaviour* the contract promises, not W6's specific data, and
 * the difference is called out in the final report.
 */
import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { settle, shot } from '../lib/browser';
import { SEED_SERIALS } from '../lib/config';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

test.describe('journeys (real backend)', () => {
  test('home: today 404 degrades gracefully, no crash', async ({ page, request }) => {
    // Tie the UI to the real backend: with only the seed cards nothing blooms today.
    const api = await request.get('/api/cards/today');
    expect(api.status()).toBe(404);

    await settle(page, '/', (p) => p.getByRole('alert').waitFor());
    // The friendly ErrorState, not a white screen or a thrown error boundary.
    await expect(page.getByText(/bloom hasn.t arrived/i)).toBeVisible();
    // The chrome is still intact — this is a graceful empty state, not a crash.
    await expect(page.getByRole('link', { name: /skip to content/i })).toHaveCount(1);
    await shot(page, '01-today');
  });

  test('dex: lists real cards, header count matches the API, filter narrows to LEGENDARY', async ({
    page,
    request,
  }) => {
    const all = await (await request.get('/api/cards')).json();
    expect(all.total).toBe(3);

    await settle(page, '/dex', (p) =>
      p.getByRole('group', { name: /filter by rarity/i }).waitFor(),
    );
    // "You've met N slimes · {total} have bloomed" — the total is the real API total.
    await expect(page.getByText(new RegExp(`${all.total} have bloomed`))).toBeVisible();
    const tilesAll = await page.locator('.ps-tile').count();
    expect(tilesAll).toBe(all.total);
    await shot(page, '03-dex');

    await page
      .getByRole('group', { name: /filter by rarity/i })
      .getByRole('button', { name: 'LEGENDARY' })
      .click();
    await page.waitForTimeout(900);
    const legendary = await (await request.get('/api/cards?rarity=LEGENDARY')).json();
    expect(legendary.items.map((c: { serial: number }) => c.serial)).toEqual([SEED_SERIALS.thundernub]);
    const tilesLegendary = await page.locator('.ps-tile').count();
    expect(tilesLegendary).toBe(legendary.total);
    await shot(page, '04-dex-legendary');
  });

  test('dex pagination is stable and sorts are deterministic (API level)', async ({ request }) => {
    // The UI only renders pager controls when total > PAGE_SIZE (24). With three seed
    // cards it never does, so pagination stability is verified where it actually lives:
    // the contract's page/size params on the real backend. Reported as a limitation.
    const pageOf = async (p: number) =>
      (await (await request.get(`/api/cards?size=1&page=${p}`)).json()) as {
        items: { serial: number }[];
        hasMore: boolean;
      };
    const [p1, p2, p3, p4] = await Promise.all([pageOf(1), pageOf(2), pageOf(3), pageOf(4)]);
    const serials = (r: { items: { serial: number }[] }) => r.items.map((c) => c.serial);

    expect(serials(p1)).toEqual([SEED_SERIALS.maxlen]);
    expect(serials(p2)).toEqual([SEED_SERIALS.thundernub]);
    expect(serials(p3)).toEqual([SEED_SERIALS.mochibo]);
    expect(serials(p4)).toEqual([]);
    // No card repeated or skipped across pages.
    const seen = [...serials(p1), ...serials(p2), ...serials(p3)];
    expect(new Set(seen).size).toBe(3);
    expect(p1.hasMore).toBe(true);
    expect(p3.hasMore).toBe(false);

    // Every documented sort returns a clean permutation of the three serials.
    const sortResults: Record<string, number[]> = {};
    for (const sort of ['newest', 'oldest', 'rarest', 'happiest']) {
      const r = await (await request.get(`/api/cards?sort=${sort}`)).json();
      const s = r.items.map((c: { serial: number }) => c.serial);
      sortResults[sort] = s;
      expect(new Set(s).size).toBe(3);
      expect([...s].sort((a, b) => a - b)).toEqual([1, 900, 65535]);
    }
    // Documented invariants we CAN observe with distinct data.
    expect(sortResults.newest).toEqual([65535, 900, 1]);
    expect(sortResults.oldest).toEqual([1, 900, 65535]);
    expect(sortResults.rarest).toEqual([65535, 900, 1]); // MYTHIC > LEGENDARY > EPIC

    mkdirSync(reportsDir, { recursive: true });
    writeFileSync(
      resolve(reportsDir, 'pagination-and-sort.json'),
      JSON.stringify(
        {
          pagination: { p1: serials(p1), p2: serials(p2), p3: serials(p3), p4: serials(p4) },
          sorts: sortResults,
          note:
            'Serial-descending tie-break is unobservable with three distinct seed cards ' +
            '(no two share a sort key); UI pager controls require total > 24 so are not rendered.',
        },
        null,
        2,
      ),
    );
  });

  test('profile + provenance: genuine rows for the card own serial (900)', async ({
    page,
    request,
  }) => {
    const serial = SEED_SERIALS.thundernub;
    const raw = await (await request.get(`/api/cards/${serial}/raw`)).json();

    await settle(page, `/slime/${serial}`, (p) => p.getByRole('button', { name: /unseal/i }).waitFor());
    await expect(page.getByRole('heading', { name: 'Thundernub' })).toBeVisible();
    await shot(page, '05-profile');

    await page.getByRole('button', { name: /unseal/i }).click();
    const rowsLoc = page.locator('[aria-labelledby="provenance-heading"] ol li');
    await rowsLoc.first().waitFor();
    await page.waitForTimeout(500);

    const displayedRows = await rowsLoc.count();
    expect(displayedRows).toBe(raw.rowCount);
    expect(displayedRows).toBe(raw.rows.length);

    // tag matches psc.<serial>.<part> for THIS card's own serial.
    const tags = await rowsLoc.evaluateAll((lis) =>
      lis.map((li) => li.querySelector('div span')?.textContent?.trim() ?? ''),
    );
    tags.forEach((tag, i) => expect(tag).toBe(`psc.${serial}.${i}`));

    // cardHash is 0x + 64 lowercase hex.
    expect(raw.cardHash).toMatch(/^0x[0-9a-f]{64}$/);
    await expect(page.getByText(raw.cardHash, { exact: false })).toBeVisible();

    await shot(page, '06-profile-provenance');
  });

  test('a nonexistent serial is a clean in-UI 404, not a crash', async ({ page, request }) => {
    // In-range but absent → API 404 → ProfilePage ErrorState (not the router NotFound).
    const api = await request.get('/api/cards/4242');
    expect(api.status()).toBe(404);

    await settle(page, '/slime/4242', (p) => p.getByRole('alert').waitFor());
    await expect(page.getByText(/no slime with that serial/i)).toBeVisible();
    // Chrome intact → graceful, not a blank crash.
    await expect(page.getByRole('link', { name: /skip to content/i })).toHaveCount(1);
    await shot(page, '09-notfound');
  });

  test('SPA fallback serves deep routes on hard refresh; /api/* is never swallowed', async ({
    page,
    request,
  }) => {
    // Hard navigation straight to a deep route must return the SPA shell (200 HTML)…
    const html = await request.get(`/slime/${SEED_SERIALS.mochibo}`);
    expect(html.status()).toBe(200);
    expect(html.headers()['content-type'] ?? '').toContain('text/html');

    // …and render the real card after hydration.
    await settle(page, `/slime/${SEED_SERIALS.mochibo}`, (p) =>
      p.getByRole('button', { name: /unseal/i }).waitFor(),
    );
    await expect(page.getByRole('heading', { name: 'Mochibo' })).toBeVisible();

    // But an unknown /api/* path is a JSON 404, NOT the SPA fallback.
    const apiMiss = await request.get('/api/nope');
    expect(apiMiss.status()).toBe(404);
    expect(apiMiss.headers()['content-type'] ?? '').toContain('application/json');
  });

  test('static screens render against the real backend (lab, bank, design)', async ({ page }) => {
    await settle(page, '/lab');
    await shot(page, '07-lab');
    await settle(page, '/bank');
    await shot(page, '08-bank');
    await settle(page, '/design');
    await shot(page, '10-design');
  });
});

test.describe('prefers-reduced-motion (real backend)', () => {
  test.use({ reducedMotion: 'reduce' });

  test('key screens still render correctly with motion reduced', async ({ page }) => {
    await settle(page, '/', (p) => p.getByRole('alert').waitFor());
    await shot(page, 'rm-01-today');
    await settle(page, '/dex', (p) =>
      p.getByRole('group', { name: /filter by rarity/i }).waitFor(),
    );
    await shot(page, 'rm-03-dex');
    await settle(page, `/slime/${SEED_SERIALS.thundernub}`, (p) =>
      p.getByRole('button', { name: /unseal/i }).waitFor(),
    );
    await page.getByRole('button', { name: /unseal/i }).click();
    await page.waitForTimeout(500);
    await shot(page, 'rm-06-profile-provenance');
  });
});
