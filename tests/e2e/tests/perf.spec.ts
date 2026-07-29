/**
 * A rough performance budget against the REAL backend: how much JavaScript the first
 * load transfers, and the largest-contentful-paint time. Values are recorded to
 * reports/perf.json for the report; assertions are deliberately loose so they catch a
 * catastrophic regression (a mock chunk shipped to prod, an un-split megabundle) without
 * flaking on a slow CI box.
 */
import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { settle } from '../lib/browser';
import { SEED_SERIALS } from '../lib/config';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

interface Budget {
  route: string;
  scriptCount: number;
  jsTransferBytes: number;
  jsEncodedBytes: number;
  jsDecodedBytes: number;
  lcpMs: number;
  scripts: string[];
}

const budgets: Budget[] = [];

async function measure(page: import('@playwright/test').Page, route: string): Promise<Budget> {
  const js = await page.evaluate(() => {
    const res = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
    const scripts = res.filter(
      (r) => r.initiatorType === 'script' || /\.m?js(\?|$)/.test(r.name),
    );
    const sum = (k: keyof PerformanceResourceTiming): number =>
      scripts.reduce((n, r) => n + ((r[k] as number) || 0), 0);
    return {
      count: scripts.length,
      transfer: sum('transferSize'),
      encoded: sum('encodedBodySize'),
      decoded: sum('decodedBodySize'),
      names: scripts.map((s) => new URL(s.name).pathname),
    };
  });

  const lcpMs = await page.evaluate(
    () =>
      new Promise<number>((res) => {
        let val = 0;
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) val = e.startTime;
          }).observe({ type: 'largest-contentful-paint', buffered: true });
        } catch {
          /* LCP unsupported — leave as 0 */
        }
        setTimeout(() => res(Math.round(val)), 1000);
      }),
  );

  const budget: Budget = {
    route,
    scriptCount: js.count,
    jsTransferBytes: js.transfer,
    jsEncodedBytes: js.encoded,
    jsDecodedBytes: js.decoded,
    lcpMs,
    scripts: js.names,
  };
  budgets.push(budget);
  return budget;
}

test.describe('performance budget (real backend)', () => {
  test('initial load transfers a reasonable amount of JS', async ({ page }) => {
    await settle(page, '/', (p) => p.getByRole('alert').waitFor(), 800);
    const b = await measure(page, '/');
    // Sanity, not a microbenchmark: a mock chunk or unsplit bundle would blow past this.
    expect(b.jsDecodedBytes, `initial JS decoded=${b.jsDecodedBytes}`).toBeLessThan(4_000_000);
    // The MSW mock worker must NOT be in a production build.
    expect(b.scripts.some((s) => /mockServiceWorker|msw/i.test(s))).toBe(false);
  });

  test('LCP on an image-heavy profile is within a loose budget', async ({ page }) => {
    await settle(page, `/slime/${SEED_SERIALS.mochibo}`, (p) =>
      p.getByRole('button', { name: /unseal/i }).waitFor(), 800);
    const b = await measure(page, `/slime/${SEED_SERIALS.mochibo}`);
    expect(b.lcpMs, `LCP=${b.lcpMs}ms`).toBeLessThan(10_000);
  });

  test.afterAll(() => {
    mkdirSync(reportsDir, { recursive: true });
    writeFileSync(resolve(reportsDir, 'perf.json'), JSON.stringify(budgets, null, 2));
  });
});
