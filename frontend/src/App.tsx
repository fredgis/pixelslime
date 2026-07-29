/**
 * Route table with per-route code splitting. Each screen is a lazy chunk, so the
 * initial bundle only carries the shell; a themed fallback covers the load.
 */
import { lazy, Suspense, type ReactElement } from 'react';
import { Route, Routes } from 'react-router-dom';
import Layout from '@/components/Layout';
import { LoadingState } from '@/components/States';

const TodayPage = lazy(() => import('@/pages/TodayPage'));
const DexPage = lazy(() => import('@/pages/DexPage'));
const ProfilePage = lazy(() => import('@/pages/ProfilePage'));
const LabPage = lazy(() => import('@/pages/LabPage'));
const BankPage = lazy(() => import('@/pages/BankPage'));
const DesignPage = lazy(() => import('@/pages/DesignPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));

export function App(): ReactElement {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route
          index
          element={
            <Suspense fallback={<LoadingState />}>
              <TodayPage />
            </Suspense>
          }
        />
        <Route
          path="dex"
          element={
            <Suspense fallback={<LoadingState label="Opening the dex…" />}>
              <DexPage />
            </Suspense>
          }
        />
        <Route
          path="slime/:serial"
          element={
            <Suspense fallback={<LoadingState />}>
              <ProfilePage />
            </Suspense>
          }
        />
        <Route
          path="lab"
          element={
            <Suspense fallback={<LoadingState label="Warming up the lab…" />}>
              <LabPage />
            </Suspense>
          }
        />
        <Route
          path="bank"
          element={
            <Suspense fallback={<LoadingState label="Counting SMILE…" />}>
              <BankPage />
            </Suspense>
          }
        />
        <Route
          path="design"
          element={
            <Suspense fallback={<LoadingState />}>
              <DesignPage />
            </Suspense>
          }
        />
        <Route
          path="*"
          element={
            <Suspense fallback={<LoadingState />}>
              <NotFoundPage />
            </Suspense>
          }
        />
      </Route>
    </Routes>
  );
}

export default App;
