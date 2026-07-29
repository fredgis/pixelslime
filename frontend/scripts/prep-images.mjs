/**
 * Optimises the three genuine card PNGs into responsive WebP variants for the mock.
 *
 * The source art (from assets/template + backend/tests/ai/output) is copied into
 * public/mock as-is; the mochibo template alone is ~2.2 MB, which would wreck LCP.
 * This one-off script (npm run gen:images) rewrites each source PNG to an optimised
 * 1024-wide PNG and emits 512w + 1024w WebP so the app can lazy-load with srcset.
 */
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import sharp from 'sharp';

const mockDir = fileURLToPath(new URL('../public/mock/', import.meta.url));

/** name → source PNG in public/mock. */
const sources = {
  mochibo: 'mochibo.png',
  nimbusnooze: 'nimbusnooze.png',
  thundersnuggle: 'thundersnuggle.png',
};

async function run() {
  for (const [name, file] of Object.entries(sources)) {
    const src = path.join(mockDir, file);
    const image = sharp(src);
    const meta = await image.metadata();
    console.log(`${name}: source ${meta.width}x${meta.height}`);

    // 512w and 1024w WebP (alpha preserved), for srcset.
    await sharp(src)
      .resize({ width: 512, withoutEnlargement: true })
      .webp({ quality: 82 })
      .toFile(path.join(mockDir, `${name}-512.webp`));
    await sharp(src)
      .resize({ width: 1024, withoutEnlargement: true })
      .webp({ quality: 86 })
      .toFile(path.join(mockDir, `${name}-1024.webp`));

    // Rewrite the source PNG as an optimised 1024-wide PNG (genuine art, smaller).
    const optimised = await sharp(src)
      .resize({ width: 1024, withoutEnlargement: true })
      .png({ compressionLevel: 9, palette: true })
      .toBuffer();
    await sharp(optimised).toFile(src);

    for (const out of [`${name}-512.webp`, `${name}-1024.webp`, file]) {
      const { size } = await sharp(path.join(mockDir, out)).toBuffer({ resolveWithObject: true }).then((r) => ({ size: r.data.length }));
      console.log(`  → ${out}  ${(size / 1024).toFixed(1)} KB`);
    }
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
