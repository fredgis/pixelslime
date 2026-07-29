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

  // ---- Targeted verification probes (tasks B / C / D) --------------------
  console.log('verification probes');
  const checks = [];

  // D. Skip-link is hidden until focused, and is the first thing Tab reaches.
  await settle(page, '/', (p) => p.getByRole('button', { name: /reveal today/i }).waitFor(), 400);
  const skip = page.getByRole('link', { name: /skip to content/i });
  const boxHidden = await skip.boundingBox();
  const hiddenOk = !boxHidden || (boxHidden.width <= 2 && boxHidden.height <= 2);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(120);
  const focusedIsSkip = await page.evaluate(() =>
    /skip to content/i.test(document.activeElement?.textContent ?? ''),
  );
  const boxShown = await skip.boundingBox();
  const shownOk = !!boxShown && boxShown.width > 20 && boxShown.height > 10;
  await shot(page, '10-skiplink-focused');
  checks.push(['D skip-link hidden off-focus (~1x1)', hiddenOk]);
  checks.push(['D skip-link is first Tab stop', focusedIsSkip]);
  checks.push(['D skip-link revealed on focus', shownOk]);

  // B. Locked SLIMEDEX tiles must leak nothing about their tier (W5 fix).
  await settle(page, '/dex', (p) => p.getByRole('group', { name: /filter by rarity/i }).waitFor(), 400);
  const locked = await page.evaluate(() => {
    const tiles = Array.from(document.querySelectorAll('.ps-tile.locked'));
    const rartag = tiles.filter((t) => t.querySelector('.ps-tile__rartag')).length;
    const undiscovered = tiles.filter((t) => t.querySelector('.ps-tile__locktag')).length;
    const TIER = /(COMMON|UNCOMMON|RARE|EPIC|LEGENDARY|MYTHIC)/i;
    const labelLeak = tiles.filter((t) => TIER.test(t.getAttribute('aria-label') ?? '')).length;
    return { count: tiles.length, rartag, undiscovered, labelLeak };
  });
  checks.push([`B locked tiles present (${locked.count})`, locked.count > 0]);
  checks.push(['B no rarity-house tag on locked tiles', locked.rartag === 0]);
  checks.push(['B locked tiles show UNDISCOVERED', locked.undiscovered === locked.count]);
  checks.push(['B no tier word in locked aria-label', locked.labelLeak === 0]);

  // C. Provenance rows carry the card's own tag, not a hardcoded serial.
  await settle(page, '/slime/14', (p) => p.getByRole('button', { name: /unseal/i }).waitFor(), 400);
  await page.getByRole('button', { name: /unseal/i }).click();
  await page.locator('[aria-labelledby="provenance-heading"] ol li').first().waitFor();
  await page.waitForTimeout(400);
  const tags = await page
    .locator('[aria-labelledby="provenance-heading"] ol li')
    .evaluateAll((lis) => lis.map((li) => li.querySelector('div span')?.textContent?.trim() ?? ''));
  const tagsOk = tags.length > 0 && tags.every((t, i) => t === `psc.14.${i}`);
  checks.push([`C provenance tags are psc.14.x [${tags.join(', ')}]`, tagsOk]);

  // V5. The panel shows the real, variable stream length (serial 14 = 183 bytes / 2 rows),
  //     never the old fixed 175. "175 bytes" survives only as the per-row constraint.
  const provText = await page.locator('[aria-labelledby="provenance-heading"]').innerText();
  const streamBytesOk = /\b183\s+BYTES/i.test(provText) && /175\s+BYTES\s*\/\s*ROW/i.test(provText);
  checks.push([`V5 panel shows real 183 bytes + "175 / row" [${streamBytesOk}]`, streamBytesOk]);

  // V3. Value column follows the codec sign convention: header row = positive YYYYMMDD
  //     mint-date key, every continuation row = negative -(serial*16+part).
  const vals = await page
    .locator('[aria-labelledby="provenance-heading"] ol li')
    .evaluateAll((lis) =>
      lis.map((li) => {
        const spans = Array.from(li.querySelectorAll('div span')).map((s) => s.textContent?.trim() ?? '');
        return spans.find((t) => t.startsWith('val:')) ?? '';
      }),
    );
  const headerPositive = /^val:\d{8}$/.test(vals[0] ?? '');
  const contNegative = vals.length > 1 && vals.slice(1).every((v) => /^val:-\d+$/.test(v));
  checks.push([`V3 header value is positive date [${vals[0] ?? ''}]`, headerPositive]);
  checks.push([`V3 continuation value is negative [${vals.slice(1).join(', ')}]`, contNegative]);

  // V4. An invalid serial (`/slime/abc`) shows the clean not-found screen, not an error/crash.
  await settle(page, '/slime/abc', null, 500);
  const notFoundText = await page.locator('body').innerText();
  const cleanNotFound = /(LOST\?|WANDERED OFF|404)/i.test(notFoundText);
  await shot(page, '11-invalid-serial-notfound');
  checks.push([`V4 /slime/abc shows clean not-found screen`, cleanNotFound]);

  console.log('  probe results:');
  let probeFails = 0;
  for (const [name, ok] of checks) {
    if (!ok) probeFails += 1;
    console.log(`    ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  }
  console.log(`  probes: ${checks.length - probeFails}/${checks.length} passed`);

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
