/**
 * W10 integration harness — the whole point of this workstream.
 *
 * Nobody had ever run the real frontend against the real backend. This script does
 * exactly that, end to end, and tears everything down cleanly (including on failure):
 *
 *   1. Build the SPA with the MSW mock DISABLED (VITE_USE_MOCK=false) so it talks to a
 *      real, same-origin /api.
 *   2. Boot the PRIMARY backend — `uvicorn app.main:app` with FAKE_BACKEND=1, in-memory
 *      asmDB + blob fakes seeded from contracts/cards/*.json, serving the built SPA from
 *      frontend/dist.
 *   3. Boot the SUPPLEMENTARY backend — `uvicorn serve_today:app`, the same real app plus
 *      one card dated today, so the reveal ceremony and /api/cards/today can be exercised.
 *   4. Wait for BOTH /api/health to return 200.
 *   5. Drive everything with Playwright.
 *   6. Kill both servers in a finally, whatever happened.
 *
 * Toggles (env): SKIP_BUILD=1, NO_TODAY=1, PRIMARY_PORT, TODAY_PORT, PW_ARGS.
 */
import { spawn } from 'node:child_process';
import { mkdirSync, createWriteStream } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..', '..');
const frontendDir = resolve(repoRoot, 'frontend');
const backendDir = resolve(repoRoot, 'backend');
const reportsDir = resolve(here, 'reports');
mkdirSync(reportsDir, { recursive: true });

const isWin = process.platform === 'win32';
const PY = process.env.PYTHON ?? 'python';
const NPM = isWin ? 'npm.cmd' : 'npm';
const NPX = isWin ? 'npx.cmd' : 'npx';

const PRIMARY_PORT = Number(process.env.PRIMARY_PORT ?? 8080);
const TODAY_PORT = Number(process.env.TODAY_PORT ?? 8081);
const PRIMARY_BASE = `http://127.0.0.1:${PRIMARY_PORT}`;
const TODAY_BASE = `http://127.0.0.1:${TODAY_PORT}`;
const WITH_TODAY = process.env.NO_TODAY !== '1';

/** Run a command to completion, inheriting stdio; reject on non-zero exit. */
function run(cmd, args, opts = {}) {
  return new Promise((resolvePromise, reject) => {
    // Node >=20 refuses to spawn .cmd/.bat (npm/npx on Windows) without a shell.
    const child = spawn(cmd, args, { stdio: 'inherit', shell: isWin, ...opts });
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolvePromise() : reject(new Error(`${cmd} ${args.join(' ')} exited ${code}`)),
    );
  });
}

/** Start a long-lived server; tee its output to console (prefixed) and a log file. */
function startServer(name, cmd, args, opts = {}) {
  const logPath = resolve(reportsDir, `${name}.log`);
  const logStream = createWriteStream(logPath);
  const child = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'], ...opts });
  const pipe = (stream) => {
    stream.on('data', (buf) => {
      const text = buf.toString();
      logStream.write(text);
      for (const line of text.split(/\r?\n/)) if (line.trim()) console.log(`[${name}] ${line}`);
    });
  };
  pipe(child.stdout);
  pipe(child.stderr);
  child.on('exit', (code) => console.log(`[${name}] process exited with code ${code}`));
  return child;
}

/** Kill a process tree by PID (PID-based, never by name). */
function killTree(child) {
  if (!child || child.exitCode !== null || child.killed) return;
  const pid = child.pid;
  if (!pid) return;
  try {
    if (isWin) spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
    else process.kill(-pid, 'SIGTERM');
  } catch (err) {
    console.error(`  failed to kill ${pid}:`, err.message);
  }
}

async function waitForHealth(base, label, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  let lastErr = 'no attempt';
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(3000) });
      if (res.status === 200) {
        const body = await res.json();
        console.log(`  ${label} healthy: ${JSON.stringify(body)}`);
        return body;
      }
      lastErr = `status ${res.status}`;
    } catch (err) {
      lastErr = err.message;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new Error(`${label} did not become healthy within ${timeoutMs}ms (last: ${lastErr})`);
}

async function main() {
  const servers = [];
  const backendEnv = {
    ...process.env,
    FAKE_BACKEND: '1',
    LOCAL_DEV: '1',
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };

  try {
    // 1) Build the SPA with the mock disabled.
    if (process.env.SKIP_BUILD === '1') {
      console.log('▶ SKIP_BUILD=1 — reusing existing frontend/dist');
    } else {
      console.log('▶ Building frontend with VITE_USE_MOCK=false …');
      await run(NPM, ['run', 'build'], {
        cwd: frontendDir,
        env: { ...process.env, VITE_USE_MOCK: 'false' },
      });
    }

    // 2) Primary backend: real app, fakes seeded from contracts/cards, serves dist.
    console.log(`▶ Starting PRIMARY backend on ${PRIMARY_BASE} …`);
    servers.push(
      startServer(
        'primary-backend',
        PY,
        ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(PRIMARY_PORT)],
        { cwd: backendDir, env: backendEnv },
      ),
    );

    // 3) Supplementary backend: same app + one card dated today.
    if (WITH_TODAY) {
      console.log(`▶ Starting SUPPLEMENTARY today backend on ${TODAY_BASE} …`);
      servers.push(
        startServer(
          'today-backend',
          PY,
          ['-m', 'uvicorn', 'serve_today:app', '--host', '127.0.0.1', '--port', String(TODAY_PORT)],
          { cwd: here, env: backendEnv },
        ),
      );
    }

    // 4) Wait for health on both.
    await waitForHealth(PRIMARY_BASE, 'PRIMARY');
    if (WITH_TODAY) await waitForHealth(TODAY_BASE, 'TODAY');

    // 5) Drive with Playwright.
    console.log('▶ Running Playwright …');
    const pwArgs = ['playwright', 'test', ...(process.env.PW_ARGS ? process.env.PW_ARGS.split(' ') : [])];
    await run(NPX, pwArgs, {
      cwd: here,
      env: {
        ...process.env,
        PRIMARY_BASE,
        TODAY_BASE: WITH_TODAY ? TODAY_BASE : '',
      },
    });

    console.log('\n✔ Harness completed: Playwright passed against the real backend.');
  } finally {
    // 6) Teardown — always.
    console.log('▶ Tearing down servers …');
    for (const s of servers) killTree(s);
  }
}

main().catch((err) => {
  console.error(`\n✘ Harness failed: ${err.message}`);
  process.exitCode = 1;
  // Give killTree a beat to fire before exit.
  setTimeout(() => process.exit(process.exitCode ?? 1), 1500);
});
