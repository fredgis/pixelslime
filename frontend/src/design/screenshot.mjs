// Dev-only Playwright screenshotter for the design-system preview.
// Usage: node screenshot.mjs [baseUrl]
// Captures the full preview page in normal and reduced-motion modes.
import { chromium } from 'playwright';

const baseUrl = process.argv[2] ?? process.env.PREVIEW_URL ?? 'http://localhost:5173/';

async function shoot({ reducedMotion, out, theme }) {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1024 },
    deviceScaleFactor: 2,
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference',
  });
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: 'networkidle' });

  // Ensure the three OFL faces are ready so there is no swap mid-screenshot.
  await page.evaluate(() => document.fonts.ready);

  if (theme === 'night') {
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'night';
    });
  }

  // Reveal the CardFlip so the emotional centrepiece is captured face-up.
  await page.getByRole('button', { name: /reveal/i }).first().click().catch(() => {});

  // Let entrance staggers + stat fills settle (everything is <=600ms).
  await page.waitForTimeout(reducedMotion ? 400 : 1400);

  await page.screenshot({ path: out, fullPage: true });
  await browser.close();
  console.log(`saved ${out} (reducedMotion=${reducedMotion}, theme=${theme ?? 'day'})`);
}

await shoot({ reducedMotion: false, out: 'preview.png', theme: 'day' });
await shoot({ reducedMotion: false, out: 'preview-night.png', theme: 'night' });
await shoot({ reducedMotion: true, out: 'preview-reduced.png', theme: 'day' });
