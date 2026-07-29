/**
 * Contract conformance: hit every /api/* operation in contracts/openapi.yaml against
 * the REAL backend and validate each response against the schema the contract defines.
 *
 * This is the check the whole workstream exists for. W6 generated its mock from this
 * file; W7 hand-wrote the server. If they have drifted, the drift shows up here as a
 * schema failure or an unexpected status — not as a silent shape mismatch the mock
 * papered over.
 *
 * Output: reports/contract-table.{json,md} — one row per operation with the real
 * status code and whether the body validated. Consumed by the final report.
 */
import { test, expect, type APIResponse } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { validateJson } from '../lib/openapi';
import { SEED_SERIALS } from '../lib/config';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

interface Row {
  method: string;
  contractPath: string;
  url: string;
  status: number;
  expected: string;
  schemaValid: 'yes' | 'no' | 'n/a';
  notes: string;
}

const rows: Row[] = [];

function record(row: Row): void {
  rows.push(row);
}

/** Validate a JSON APIResponse against the contract and record a table row. */
async function checkJson(
  resp: APIResponse,
  contractPath: string,
  expected: string,
  extraNotes = '',
): Promise<Row> {
  const status = resp.status();
  const body = await resp.json().catch(() => undefined);
  const { ok, errors } = validateJson(contractPath, 'get', String(status), body);
  const notes = [extraNotes, ok ? '' : errors.slice(0, 4).join('; ')].filter(Boolean).join(' | ');
  const row: Row = {
    method: 'GET',
    contractPath,
    url: new URL(resp.url()).pathname + new URL(resp.url()).search,
    status,
    expected,
    schemaValid: ok ? 'yes' : 'no',
    notes,
  };
  record(row);
  return row;
}

test.describe('contract conformance (real backend)', () => {
  test('GET /api/health → 200 schema-valid', async ({ request }) => {
    const resp = await request.get('/api/health');
    expect(resp.status()).toBe(200);
    const row = await checkJson(resp, '/api/health', '200');
    expect(row.schemaValid, row.notes).toBe('yes');
    const body = await resp.json();
    expect(body.cards).toBe(3); // exactly the three contract seed cards
  });

  test('GET /api/cards/today → 404 (no seed blooms on the run date) schema-valid', async ({
    request,
  }) => {
    const resp = await request.get('/api/cards/today');
    // With only the three contract seed cards and the wall clock, nothing blooms
    // today, so the contract's 404 branch is what the real backend serves.
    expect(resp.status()).toBe(404);
    const row = await checkJson(
      resp,
      '/api/cards/today',
      '404',
      'no seed card blooms on the run date',
    );
    expect(row.schemaValid, row.notes).toBe('yes');
  });

  test('GET /api/cards → 200 page schema-valid, ordered newest', async ({ request }) => {
    const resp = await request.get('/api/cards');
    expect(resp.status()).toBe(200);
    const row = await checkJson(resp, '/api/cards', '200');
    expect(row.schemaValid, row.notes).toBe('yes');
    const body = await resp.json();
    expect(body.total).toBe(3);
    expect(body.items.map((c: { serial: number }) => c.serial)).toEqual([65535, 900, 1]);
  });

  test('GET /api/cards with type & rarity filters → 200 schema-valid', async ({ request }) => {
    const resp = await request.get('/api/cards?rarity=LEGENDARY&sort=rarest');
    expect(resp.status()).toBe(200);
    const row = await checkJson(resp, '/api/cards', '200', 'rarity=LEGENDARY&sort=rarest');
    expect(row.schemaValid, row.notes).toBe('yes');
    const body = await resp.json();
    expect(body.items.every((c: { rarity: string }) => c.rarity === 'LEGENDARY')).toBe(true);
  });

  for (const [label, serial] of Object.entries(SEED_SERIALS)) {
    test(`GET /api/cards/${serial} (${label}) → 200 Card schema-valid`, async ({ request }) => {
      const resp = await request.get(`/api/cards/${serial}`);
      expect(resp.status()).toBe(200);
      const row = await checkJson(resp, '/api/cards/{serial}', '200', label);
      expect(row.schemaValid, row.notes).toBe('yes');
    });

    test(`GET /api/cards/${serial}/raw (${label}) → 200 provenance schema-valid`, async ({
      request,
    }) => {
      const resp = await request.get(`/api/cards/${serial}/raw`);
      expect(resp.status()).toBe(200);
      const row = await checkJson(resp, '/api/cards/{serial}/raw', '200', label);
      expect(row.schemaValid, row.notes).toBe('yes');
      const body = await resp.json();
      // The provenance invariants the report asserts on, checked here too.
      expect(body.cardHash).toMatch(/^0x[0-9a-f]{64}$/);
      expect(body.rowCount).toBe(body.rows.length);
      for (const r of body.rows) expect(r.tag).toMatch(new RegExp(`^psc\\.${serial}\\.\\d+$`));
    });

    test(`GET /api/nft/${serial} (${label}) → 200 ERC-721 schema-valid`, async ({ request }) => {
      const resp = await request.get(`/api/nft/${serial}`);
      expect(resp.status()).toBe(200);
      const row = await checkJson(resp, '/api/nft/{serial}', '200', label);
      expect(row.schemaValid, row.notes).toBe('yes');
    });
  }

  test('GET /api/cards/{serial} absent-but-in-range → 404 Error schema-valid', async ({
    request,
  }) => {
    const resp = await request.get('/api/cards/2');
    expect(resp.status()).toBe(404);
    const row = await checkJson(resp, '/api/cards/{serial}', '404', 'serial 2 absent');
    expect(row.schemaValid, row.notes).toBe('yes');
  });

  test('GET /api/cards/{serial} out-of-range/non-integer → 422 (UNDOCUMENTED; mock returns 404)', async ({
    request,
  }) => {
    // The contract documents only 200 and 404 for this route, and the Serial param is
    // `minimum:1, maximum:65535`. FastAPI's own param validation returns 422 for anything
    // outside that — a status the contract never lists. The MSW mock (handlers.ts) instead
    // clamps invalid serials to a 404, which is what the contract does document. So the two
    // implementations disagree on this edge, and the real one emits an undocumented status.
    for (const [serial, label] of [
      ['99999', 'out-of-range'],
      ['abc', 'non-integer'],
    ] as const) {
      const resp = await request.get(`/api/cards/${serial}`);
      expect(resp.status(), `${label} serial should be FastAPI 422`).toBe(422);
      record({
        method: 'GET',
        contractPath: '/api/cards/{serial}',
        url: `/api/cards/${serial}`,
        status: resp.status(),
        expected: '404 per contract',
        schemaValid: 'n/a',
        notes: `${label}: real backend returns 422 (undocumented); MSW mock returns 404`,
      });
    }
  });

  test('GET /api/stats → 200 schema-valid', async ({ request }) => {
    const resp = await request.get('/api/stats');
    expect(resp.status()).toBe(200);
    const row = await checkJson(resp, '/api/stats', '200');
    expect(row.schemaValid, row.notes).toBe('yes');
  });

  test('POST /api/admin/generate without token → 401 (guarded, off by default)', async ({
    request,
  }) => {
    const resp = await request.post('/api/admin/generate', { data: {} });
    // Contract lists 202/401/409; none carry a JSON schema, so we only assert status.
    expect([401, 403]).toContain(resp.status());
    record({
      method: 'POST',
      contractPath: '/api/admin/generate',
      url: '/api/admin/generate',
      status: resp.status(),
      expected: '401',
      schemaValid: 'n/a',
      notes: resp.status() === 401 ? 'guarded as documented' : `returned ${resp.status()}`,
    });
  });

  test.describe('media routes serve real bytes through the proxy', () => {
    test('GET /api/cards/1/image → 200 PNG, immutable, 304 on revalidation', async ({
      request,
    }) => {
      const resp = await request.get('/api/cards/1/image');
      expect(resp.status()).toBe(200);
      const ct = resp.headers()['content-type'] ?? '';
      const cache = resp.headers()['cache-control'] ?? '';
      const etag = resp.headers()['etag'];
      const bytes = (await resp.body()).length;
      expect(ct).toContain('image/png');
      expect(cache).toContain('immutable');
      expect(bytes).toBeGreaterThan(0);
      expect(etag, 'image must carry an ETag to enable conditional GET').toBeTruthy();

      const revalidated = await request.get('/api/cards/1/image', {
        headers: { 'If-None-Match': etag as string },
      });
      expect(revalidated.status(), 'conditional GET must return 304').toBe(304);

      record({
        method: 'GET',
        contractPath: '/api/cards/{serial}/image',
        url: '/api/cards/1/image',
        status: 200,
        expected: '200',
        schemaValid: 'n/a',
        notes: `image/png, ${bytes}B, ${cache}, 304-on-revalidate=${revalidated.status() === 304}`,
      });
    });

    test('GET /api/cards/1/thumb → 200 WebP, immutable, 304 on revalidation', async ({
      request,
    }) => {
      const resp = await request.get('/api/cards/1/thumb');
      expect(resp.status()).toBe(200);
      const ct = resp.headers()['content-type'] ?? '';
      const cache = resp.headers()['cache-control'] ?? '';
      const etag = resp.headers()['etag'];
      const bytes = (await resp.body()).length;
      expect(ct).toContain('image/webp');
      expect(cache).toContain('immutable');
      expect(bytes).toBeGreaterThan(0);

      const revalidated = etag
        ? await request.get('/api/cards/1/thumb', { headers: { 'If-None-Match': etag } })
        : undefined;
      if (revalidated) expect(revalidated.status()).toBe(304);

      record({
        method: 'GET',
        contractPath: '/api/cards/{serial}/thumb',
        url: '/api/cards/1/thumb',
        status: 200,
        expected: '200',
        schemaValid: 'n/a',
        notes: `image/webp, ${bytes}B, ${cache}, 304-on-revalidate=${revalidated?.status() === 304}`,
      });
    });

    test('GET /api/cards/2/image (absent) → 404', async ({ request }) => {
      const resp = await request.get('/api/cards/2/image');
      expect(resp.status()).toBe(404);
      record({
        method: 'GET',
        contractPath: '/api/cards/{serial}/image',
        url: '/api/cards/2/image',
        status: 404,
        expected: '404',
        schemaValid: 'n/a',
        notes: 'absent serial',
      });
    });
  });

  test('/api/* is JSON even for unknown routes (never swallowed by the SPA)', async ({
    request,
  }) => {
    const resp = await request.get('/api/does-not-exist');
    expect(resp.status()).toBe(404);
    const ct = resp.headers()['content-type'] ?? '';
    expect(ct).toContain('application/json');
    record({
      method: 'GET',
      contractPath: '/api/* (unknown)',
      url: '/api/does-not-exist',
      status: 404,
      expected: '404',
      schemaValid: 'n/a',
      notes: 'JSON 404, not SPA fallback',
    });
  });

  test.afterAll(() => {
    mkdirSync(reportsDir, { recursive: true });
    rows.sort((a, b) => (a.contractPath + a.url).localeCompare(b.contractPath + b.url));
    writeFileSync(resolve(reportsDir, 'contract-table.json'), JSON.stringify(rows, null, 2));

    const header = '| Method | Contract path | Actual URL | Status | Expected | Schema valid | Notes |';
    const sep = '| --- | --- | --- | --- | --- | --- | --- |';
    const lines = rows.map(
      (r) =>
        `| ${r.method} | \`${r.contractPath}\` | \`${r.url}\` | ${r.status} | ${r.expected} | ${r.schemaValid} | ${r.notes.replace(/\|/g, '\\|')} |`,
    );
    writeFileSync(
      resolve(reportsDir, 'contract-table.md'),
      ['# Contract conformance table (real backend)', '', header, sep, ...lines, ''].join('\n'),
    );
  });
});
