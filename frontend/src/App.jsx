import { lazy } from 'react'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Toast'
import { FiltersProvider } from './hooks/useFilters'

// One chunk per page: Recharts and page code load only when a page is opened.
const Overview = lazy(() => import('./pages/Overview'))
const Sentiment = lazy(() => import('./pages/Sentiment'))
const Trends = lazy(() => import('./pages/Trends'))
const Topics = lazy(() => import('./pages/Topics'))
const Engagement = lazy(() => import('./pages/Engagement'))
const Audience = lazy(() => import('./pages/Audience'))
const Anomalies = lazy(() => import('./pages/Anomalies'))
const Explorer = lazy(() => import('./pages/Explorer'))
const Performance = lazy(() => import('./pages/Performance'))
const Ingestion = lazy(() => import('./pages/Ingestion'))
const AboutDataset = lazy(() => import('./pages/AboutDataset'))

function NotFound() {
  return (
    <div className="py-20 text-center">
      <p className="text-lg font-semibold text-ink">Page not found</p>
      <Link to="/" className="mt-2 inline-block text-sm text-accent hover:underline">Back to overview</Link>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <FiltersProvider>
        <ToastProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Overview />} />
              <Route path="sentiment" element={<Sentiment />} />
              <Route path="trends" element={<Trends />} />
              <Route path="topics" element={<Topics />} />
              <Route path="engagement" element={<Engagement />} />
              <Route path="audience" element={<Audience />} />
              <Route path="anomalies" element={<Anomalies />} />
              <Route path="explorer" element={<Explorer />} />
              <Route path="performance" element={<Performance />} />
              <Route path="ingestion" element={<Ingestion />} />
              <Route path="dataset" element={<AboutDataset />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ToastProvider>
      </FiltersProvider>
    </BrowserRouter>
  )
}
