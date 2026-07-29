// Dev-only accessibility audit of the design-system preview using axe-core.
// Usage: node axe-check.mjs [baseUrl]
import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';

const baseUrl = process.argv[2] ?? 'http://localhost:5173/';
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1024 } });
const page = await context.newPage();
await page.goto(baseUrl, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(500);

const results = await new AxeBuilder({ page })
  .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
  .analyze();

const v = results.violations;
console.log(`\naxe violations: ${v.length}`);
for (const violation of v) {
  console.log(`\n  [${violation.impact}] ${violation.id} — ${violation.help}`);
  console.log(`   ${violation.helpUrl}`);
  for (const node of violation.nodes) {
    console.log(`   → ${node.target.join(' ')}`);
    console.log(`     ${node.failureSummary?.replace(/\n/g, '\n     ')}`);
  }
}
console.log(`\npasses: ${results.passes.length}, incomplete: ${results.incomplete.length}`);
for (const inc of results.incomplete) {
  console.log(`  ~ ${inc.id} (${inc.nodes.length} node/s need manual review) — ${inc.help}`);
}
await browser.close();
process.exit(v.length > 0 ? 1 : 0);
