/**
 * Materialise the reference card the design preview imports.
 *
 * `src/design/preview.tsx` does `import mochibo from './preview-assets/mochibo.png'`,
 * but that directory is deliberately not tracked: the canonical card already lives at
 * `assets/template/mochibo.png` and committing a second 2.3 MB copy of the same binary
 * is how a repository ends up with two subtly different versions of its own reference.
 *
 * So the build materialises it instead. Without this, `npm run build` fails on a fresh
 * clone and inside Docker — which is exactly how it was found.
 *
 * Runs automatically via the `prebuild` and `predev` hooks.
 */
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '..', '..');

const source = resolve(repoRoot, 'assets', 'template', 'mochibo.png');
const target = resolve(here, '..', 'src', 'design', 'preview-assets', 'mochibo.png');

if (!existsSync(source)) {
  console.error(
    `[prepare:assets] canonical reference card missing at ${source}\n` +
      '  This is the style reference the whole card pipeline is built on; the repository ' +
      'is incomplete without it.',
  );
  process.exit(1);
}

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`[prepare:assets] reference card -> ${target.replace(repoRoot, '.')}`);
