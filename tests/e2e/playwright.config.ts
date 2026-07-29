import { defineConfig, devices } from '@playwright/test';
import { PRIMARY_BASE, VIEWPORT } from './lib/config';

/**
 * The harness (harness.mjs) builds the mock-off SPA, boots the real backend(s),
 * waits for health, and only then invokes `playwright test`. So these specs assume
 * a live server at PRIMARY_BASE and do NOT manage a webServer themselves.
 *
 * workers: 1 — the backend is a single shared, stateful fake; serial runs keep the
 * request log, rate limiter and any discovery state deterministic.
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    ['json', { outputFile: 'reports/playwright-results.json' }],
    ['html', { outputFolder: 'reports/html', open: 'never' }],
  ],
  outputDir: 'reports/test-results',
  use: {
    baseURL: PRIMARY_BASE,
    viewport: VIEWPORT,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: VIEWPORT },
    },
  ],
});
