/**
 * App entry point.
 *
 * Order matters: emit the Tailwind utility layer (index.css) then the design system's
 * globals.css exactly once here (fonts, `.ps-*` classes, keyframes, theme vars, the
 * central reduced-motion rule) — globals.css comes second so its base wins any overlap
 * with Tailwind preflight. Then start the Mock Service Worker *before* React renders when
 * VITE_USE_MOCK is on, and mount the router. The worker is dynamically imported so none
 * of the mock reaches a real-API build.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import './index.css';
import '@/design/globals.css';
import App from './App';
import { USE_MOCK } from './lib/config';
import { useSettingsStore } from './store/settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: USE_MOCK ? false : 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** Apply the persisted theme before first paint to avoid a flash. */
function applyInitialTheme(): void {
  const { theme } = useSettingsStore.getState();
  document.documentElement.dataset.theme = theme === 'night' ? 'night' : '';
}

async function enableMocking(): Promise<void> {
  // Inline the flag from `import.meta.env` (not the config helper) so Rollup can
  // constant-fold it: a plain `npm run build` drops this dynamic import — and the
  // whole ~300 KB mock chunk — while `VITE_USE_MOCK=true` keeps it for demos/tests.
  const flag = import.meta.env.VITE_USE_MOCK;
  const useMock = flag === 'true' || flag === '1' || ((flag === undefined || flag === '') && import.meta.env.DEV);
  if (!useMock) return;
  const { worker } = await import('./mocks/browser');
  await worker.start({
    onUnhandledRequest: 'bypass',
    quiet: true,
    serviceWorker: { url: `${import.meta.env.BASE_URL}mockServiceWorker.js` },
  });
}

function mount(): void {
  const container = document.getElementById('root');
  if (!container) throw new Error('Root element #root not found');
  createRoot(container).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

applyInitialTheme();
void enableMocking().then(mount);
