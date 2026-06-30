import { lazy, Suspense, type ReactNode } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuthStore } from './store/useAuthStore'

const HomePage = lazy(() => import('./pages/HomePage'))
const PortfolioPage = lazy(() => import('./pages/PortfolioPage'))
const StockDetailPage = lazy(() => import('./pages/StockDetailPage'))
const LimitUpPage = lazy(() => import('./pages/LimitUpPage'))
const LimitUpAnalysisPage = lazy(() => import('./pages/LimitUpAnalysisPage'))
const StockListPage = lazy(() => import('./pages/StockListPage'))
const ChanlunBuySignalsPage = lazy(() => import('./pages/ChanlunBuySignalsPage'))
const StrategiesPage = lazy(() => import('./pages/StrategiesPage'))
const TailEndMonitorPage = lazy(() => import('./pages/TailEndMonitorPage'))
const BacktestPage = lazy(() => import('./pages/BacktestPage'))
const AnalysisPage = lazy(() => import('./pages/AnalysisPage'))
const AnalysisDetailPage = lazy(() => import('./pages/AnalysisDetailPage'))
const RawSourcesPage = lazy(() => import('./pages/RawSourcesPage'))
const RawSourceDetailPage = lazy(() => import('./pages/RawSourceDetailPage'))
const ManualMaterialsPage = lazy(() => import('./pages/ManualMaterialsPage'))
const ManualSourceNewPage = lazy(() => import('./pages/ManualSourceNewPage'))
const RawSourceEditPage = lazy(() => import('./pages/RawSourceEditPage'))
const DailyTradeLogPage = lazy(() => import('./pages/DailyTradeLogPage'))
const SectorsPage = lazy(() => import('./pages/SectorsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const WikiHomePage = lazy(() => import('./pages/WikiHomePage'))
const WikiPageDetailPage = lazy(() => import('./pages/WikiPageDetailPage'))
const WikiIngestPage = lazy(() => import('./pages/WikiIngestPage'))
const WikiLintPage = lazy(() => import('./pages/WikiLintPage'))
const WikiClaimsPage = lazy(() => import('./pages/WikiClaimsPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))

function PageFallback() {
  return <div className="empty-state">加载中...</div>
}

function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return children
}

function AppRoutes() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/stock" element={<StockDetailPage />} />
        <Route path="/limit-up" element={<LimitUpPage />} />
        <Route path="/limit-up-analysis" element={<LimitUpAnalysisPage />} />
        <Route path="/stocks" element={<StockListPage />} />
<Route path="/chanlun" element={<ChanlunBuySignalsPage />} />
        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/tail-end-monitor" element={<TailEndMonitorPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/analysis/:jobId" element={<AnalysisDetailPage />} />
        <Route path="/sectors" element={<SectorsPage />} />
        <Route path="/knowledge/raw" element={<RawSourcesPage />} />
        <Route path="/knowledge/manual" element={<ManualMaterialsPage />} />
        <Route path="/knowledge/raw/new" element={<ManualSourceNewPage />} />
        <Route path="/knowledge/raw/:sourceId/edit" element={<RawSourceEditPage />} />
        <Route path="/knowledge/raw/:sourceId" element={<RawSourceDetailPage />} />
        <Route path="/trades/daily" element={<DailyTradeLogPage />} />
        <Route path="/wiki" element={<WikiHomePage />} />
        <Route path="/wiki/ingest" element={<WikiIngestPage />} />
        <Route path="/wiki/lint" element={<WikiLintPage />} />
        <Route path="/wiki/claims" element={<WikiClaimsPage />} />
        <Route path="/wiki/pages/:pageId" element={<WikiPageDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={(
            <RequireAuth>
              <AppRoutes />
            </RequireAuth>
          )}
        />
      </Routes>
    </Suspense>
  )
}
