/**
 * Drives the running dev server with Playwright to:
 *   1. screenshot all five screens (+ /design) in the default (day) theme,
 *   2. exercise the real interactions (flip today's card, filter the dex,
 *      unseal a profile's provenance panel) and screenshot the results,
 *   3. repeat the screens with prefers-reduced-motion emulated,
 *   4. run @axe-core/playwright on every screen and report violation counts.
 *
 * Usage: `npm run dev` in one shell, then `npm run shot` (or `node scripts/screenshots.mjs`).
 * Everything is served from the MSW mock, so no real backend is required.
 */
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const BASE = process.env.SHOT_BASE ?? 'http://localhost:5173';
const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, '..', 'screenshots');

const VIEWPORT = { width: 1440, height: 960 };
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

/** Wait for a route to be visually settled: load, a ready cue, then animation time. */
async function settle(page, path, ready, ms = 1400) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle').catch(() => {});
  if (ready) {
    await ready(page).catch(() => {});
  }
  await page.waitForTimeout(ms);
}

async function shot(page, name) {
  const path = resolve(outDir, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  console.log(`  · ${name}.png`);
}

/** Run axe on the current page and return a compact violation summary. */
async function audit(page, route) {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const violations = results.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    nodes: v.nodes.length,
    help: v.help,
  }));
  return { route, total: violations.length, violations };
}

async function main() {
  await mkdir(outDir, { recursive: true });
  const browser = await chromium.launch();
  const axeReport = [];

  // ---- Default (day) theme: screens + interactions ------------------------
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.error('  ! pageerror:', e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') console.error('  ! console.error:', m.text());
  });

  console.log('Default theme — screens & interactions');

  // ① TODAY — face down, then flip.
  await settle(page, '/', (p) => p.getByRole('button', { name: /reveal today/i }).waitFor());
  await shot(page, '01-today-facedown');
  await page.getByRole('button', { name: /reveal today/i }).click();
  await page.waitForTimeout(2200); // flip + stat cascade + confetti/ceremony
  await shot(page, '02-today-revealed');

  // ② SLIMEDEX — full gallery, then filtered to LEGENDARY.
  await settle(page, '/dex', (p) => p.getByRole('group', { name: /filter by rarity/i }).waitFor());
  const tilesAll = await page.locator('.ps-tile').count();
  await shot(page, '03-dex');
  await page.getByRole('group', { name: /filter by rarity/i }).getByRole('button', { name: 'LEGENDARY' }).click();
  await page.waitForTimeout(900);
  const tilesLegendary = await page.locator('.ps-tile').count();
  await shot(page, '04-dex-legendary');
  console.log(`  dex tiles: all=${tilesAll}, legendary=${tilesLegendary}`);

  // ③ SLIME PROFILE — full card, then unseal provenance.
  await settle(page, '/slime/14', (p) => p.getByRole('button', { name: /unseal/i }).waitFor());
  await shot(page, '05-profile');
  await page.getByRole('button', { name: /unseal/i }).click();
  await page.locator('[aria-labelledby="provenance-heading"] ol li').first().waitFor();
  await page.waitForTimeout(600);
  const rowCount = await page.locator('[aria-labelledby="provenance-heading"] ol li').count();
  const codeRows = await page.locator('[aria-labelledby="provenance-heading"] ol li code').count();
  await shot(page, '06-profile-provenance');
  console.log(`  provenance rows: <li>=${rowCount}, Z85 <code>=${codeRows}`);

  // ④ PUNI LAB
  await settle(page, '/lab');
  await shot(page, '07-lab');

  // ⑤ SMILE BANK
  await settle(page, '/bank');
  await shot(page, '08-bank');

  // /design inspection route
  await settle(page, '/design');
  await shot(page, '09-design');

  await ctx.close();

  // ---- Reduced-motion pass -----------------------------------------------
  console.log('prefers-reduced-motion');
  const rmCtx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  const rm = await rmCtx.newPage();
  await settle(rm, '/', (p) => p.getByRole('button', { name: /reveal today/i }).waitFor());
  await shot(rm, 'rm-01-today-facedown');
  await rm.getByRole('button', { name: /reveal today/i }).click();
  await rm.waitForTimeout(1200);
  await shot(rm, 'rm-02-today-revealed');
  await settle(rm, '/dex', (p) => p.getByRole('group', { name: /filter by rarity/i }).waitFor());
  await shot(rm, 'rm-03-dex');
  await settle(rm, '/slime/14', (p) => p.getByRole('button', { name: /unseal/i }).waitFor());
  await rm.getByRole('button', { name: /unseal/i }).click();
  await rm.waitForTimeout(600);
  await shot(rm, 'rm-04-profile-provenance');
  await settle(rm, '/lab');
  await shot(rm, 'rm-05-lab');
  await settle(rm, '/bank');
  await shot(rm, 'rm-06-bank');
  await rmCtx.close();

  // ---- Accessibility audit ------------------------------------------------
  console.log('axe-core audit');
  const aCtx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1, reducedMotion: 'reduce' });
  const ap = await aCtx.newPage();
  const routes = [
    ['/', (p) => p.getByRole('button', { name: /reveal today/i }).waitFor()],
    ['/dex', (p) => p.getByRole('group', { name: /filter by rarity/i }).waitFor()],
    ['/slime/14', (p) => p.getByRole('button', { name: /unseal/i }).waitFor()],
    ['/lab', null],
    ['/bank', null],
  ];
  for (const [route, ready] of routes) {
    await settle(ap, route, ready, 600);
    if (route === '/slime/14') {
      await ap.getByRole('button', { name: /unseal/i }).click();
      await ap.waitForTimeout(500);
    }
    const report = await audit(ap, route);
    axeReport.push(report);
    console.log(`  ${route.padEnd(12)} violations=${report.total}` +
      (report.total ? ` [${report.violations.map((v) => `${v.id}(${v.impact},${v.nodes})`).join(', ')}]` : ''));
  }
  await aCtx.close();

  await writeFile(resolve(outDir, 'axe-report.json'), JSON.stringify(axeReport, null, 2), 'utf8');
  await browser.close();

  const totalViolations = axeReport.reduce((n, r) => n + r.total, 0);
  console.log(`\nDone. Screenshots in ${outDir}. Total axe violations: ${totalViolations}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
