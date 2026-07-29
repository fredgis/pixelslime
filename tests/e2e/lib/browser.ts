/**
 * Small Playwright helpers shared by the journey, a11y and perf specs. They mirror the
 * timing and screenshot conventions of frontend/scripts/screenshots.mjs (W6's mock-driven
 * script) so the two screenshot sets are captured the same way and can be compared fairly.
 */
import type { Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
export const SCREENSHOT_DIR = resolve(here, '..', 'screenshots');

/** Navigate to a route and wait for it to be visually settled (mirrors W6's `settle`). */
export async function settle(
  page: Page,
  path: string,
  ready?: (p: Page) => Promise<unknown>,
  ms = 1200,
): Promise<void> {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  if (ready) await ready(page).catch(() => {});
  await page.waitForTimeout(ms);
}

/** Full-page screenshot into tests/e2e/screenshots, named to mirror W6's set. */
export async function shot(page: Page, name: string): Promise<string> {
  mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const path = resolve(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  return path;
}
