/**
 * The flagship reveal ceremony — only runnable against the SUPPLEMENTARY backend
 * (tests/e2e/serve_today.py), which adds one synthetic card dated today so that
 * /api/cards/today returns 200. Skips cleanly when TODAY_BASE is unset.
 *
 * Two things are proven here that the pure seed cannot show:
 *   1. Clicking / keyboard-activating the face-down card reveals the REAL card served
 *      by the real backend, and the stat bars match /api/cards/today exactly.
 *   2. The top-level `dayNumber` the contract says is "Always equal to card.dayNumber"
 *      is computed by the backend as `index.size`, while `card.dayNumber` is the serial.
 *      With a today card whose serial is not the maximum, the two diverge — a latent
 *      W7 defect the natural (contiguous, newest-is-today) case would have masked.
 */
import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { settle, shot } from '../lib/browser';
import { TODAY_BASE } from '../lib/config';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

test.describe('today reveal ceremony (supplementary backend)', () => {
  test.skip(!TODAY_BASE, 'TODAY_BASE unset — supplementary today backend not running');
  test.use({ baseURL: TODAY_BASE });

  test('reveal shows the real today card and stat bars match /api/cards/today', async ({
    page,
    request,
  }) => {
    const today = await (await request.get('/api/cards/today')).json();
    const card = today.card;

    await settle(page, '/', (p) => p.getByRole('button', { name: /reveal today/i }).waitFor());
    await shot(page, '02a-today-facedown');

    await page.getByRole('button', { name: /reveal today/i }).click();
    await page.waitForTimeout(2200); // flip + stat cascade + (EPIC) confetti/shake

    // The revealed detail panel is the real card the API served.
    await expect(page.getByRole('heading', { name: card.name })).toBeVisible();
    await expect(page.getByText(card.cardId, { exact: false })).toBeVisible();

    // The four stat bars carry exactly the API's values, in order.
    const order: Array<'strength' | 'endurance' | 'agility' | 'happiness'> = [
      'strength',
      'endurance',
      'agility',
      'happiness',
    ];
    const bars = page.getByRole('progressbar');
    await expect(bars).toHaveCount(order.length);
    for (let i = 0; i < order.length; i += 1) {
      await expect(bars.nth(i)).toHaveAttribute('aria-valuenow', String(card[order[i]]));
    }

    await shot(page, '02-today-revealed');
  });

  test('top-level dayNumber diverges from card.dayNumber (contract says equal)', async ({
    request,
  }) => {
    const today = await (await request.get('/api/cards/today')).json();
    const topLevel = today.dayNumber;
    const cardDayNumber = today.card.dayNumber;
    const serial = today.card.serial;

    mkdirSync(reportsDir, { recursive: true });
    writeFileSync(
      resolve(reportsDir, 'today-daynumber.json'),
      JSON.stringify(
        {
          topLevelDayNumber: topLevel,
          cardDayNumber: cardDayNumber,
          serial,
          contract:
            'openapi.yaml: top-level dayNumber "Always equal to card.dayNumber"; ' +
            'card.dayNumber "1-based bloom ordinal".',
          backend:
            'routes_cards.get_today sets top-level dayNumber = index.size; ' +
            'serialize.card_detail sets card.dayNumber = card.serial. They coincide only when ' +
            'the today card is the highest serial in a contiguous index.',
          divergent: topLevel !== cardDayNumber,
        },
        null,
        2,
      ),
    );

    // Documented W7 defect: with a synthetic today card (serial 2) below the max serial
    // (65535), index.size (4) != serial (2). We assert the divergence so the harness
    // records the bug rather than failing on it.
    expect(cardDayNumber).toBe(serial);
    expect(topLevel).not.toBe(cardDayNumber);
  });
});
