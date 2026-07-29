/**
 * `/design` — renders W5's design-system preview verbatim, so the component gallery
 * stays inspectable inside the real app. Lazy-loaded like every other route.
 */
import type { ReactElement } from 'react';
import Preview from '@/design/preview';

export function DesignPage(): ReactElement {
  return (
    <section aria-labelledby="design-heading">
      <h1 id="design-heading" className="mb-6 font-pixel text-[18px] text-ink">
        DESIGN SYSTEM
      </h1>
      <Preview />
    </section>
  );
}

export default DesignPage;
