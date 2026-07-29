/**
 * Accessibility audit against the REAL backend, mirroring frontend/scripts/screenshots.mjs:
 * the same five screens, the same WCAG tag set, axe-core run per screen. Writes
 * reports/axe-report.json (per-screen violation counts) for direct comparison with W6's
 * mock-driven frontend/screenshots/axe-report.json.
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { settle } from '../lib/browser';
import { AXE_TAGS, SEED_SERIALS } from '../lib/config';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

interface AxeScreen {
  route: string;
  total: number;
  violations: { id: string; impact: string | null | undefined; nodes: number; help: string }[];
}

const report: AxeScreen[] = [];

async function audit(page: import('@playwright/test').Page, route: string): Promise<AxeScreen> {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const violations = results.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.length,
    help: v.help,
  }));
  const screen: AxeScreen = { route, total: violations.length, violations };
  report.push(screen);
  return screen;
}

test.describe('accessibility (axe-core, real backend)', () => {
  // Reduced motion during the audit matches W6's audit pass and keeps axe stable.
  test.use({ reducedMotion: 'reduce' });

  test('home (today 404 state)', async ({ page }) => {
    await settle(page, '/', (p) => p.getByRole('alert').waitFor(), 600);
    const screen = await audit(page, '/');
    expect(screen.total, JSON.stringify(screen.violations)).toBe(0);
  });

  test('dex', async ({ page }) => {
    await settle(page, '/dex', (p) => p.getByRole('group', { name: /filter by rarity/i }).waitFor(), 600);
    const screen = await audit(page, '/dex');
    expect(screen.total, JSON.stringify(screen.violations)).toBe(0);
  });

  test('profile (with provenance unsealed)', async ({ page }) => {
    await settle(page, `/slime/${SEED_SERIALS.thundernub}`, (p) =>
      p.getByRole('button', { name: /unseal/i }).waitFor(), 600);
    await page.getByRole('button', { name: /unseal/i }).click();
    await page.waitForTimeout(500);
    const screen = await audit(page, `/slime/${SEED_SERIALS.thundernub}`);
    expect(screen.total, JSON.stringify(screen.violations)).toBe(0);
  });

  test('lab', async ({ page }) => {
    await settle(page, '/lab', undefined, 600);
    const screen = await audit(page, '/lab');
    expect(screen.total, JSON.stringify(screen.violations)).toBe(0);
  });

  test('bank', async ({ page }) => {
    await settle(page, '/bank', undefined, 600);
    const screen = await audit(page, '/bank');
    expect(screen.total, JSON.stringify(screen.violations)).toBe(0);
  });

  test.afterAll(() => {
    mkdirSync(reportsDir, { recursive: true });
    writeFileSync(resolve(reportsDir, 'axe-report.json'), JSON.stringify(report, null, 2));
  });
});
