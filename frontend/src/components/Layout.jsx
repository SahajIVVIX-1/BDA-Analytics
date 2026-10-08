import { Suspense, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Activity, BarChart3, Gauge, Globe2, Hash, Layers, LayoutDashboard, Menu, Moon, Search, Smile, Sun, Upload, X, Zap,
} from 'lucide-react'
import FilterBar from './FilterBar'
import { Skeleton } from './ui'
import { useApi } from '../hooks/useApi'
import { fmtCompact } from '../utils/format'

export const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/sentiment', label: 'Sentiment', icon: Smile },
  { to: '/trends', label: 'Trends', icon: Hash },
  { to: '/topics', label: 'Topics', icon: Layers },
  { to: '/engagement', label: 'Engagement', icon: Zap },
  { to: '/audience', label: 'Geography & language', icon: Globe2 },
  { to: '/anomalies', label: 'Anomalies', icon: Activity },
  { to: '/explorer', label: 'Data explorer', icon: Search },
  { to: '/performance', label: 'Performance', icon: Gauge },
  { to: '/ingestion', label: 'Ingestion', icon: Upload },
]

// Pages where the global filter bar does not apply.
const NO_FILTERS = ['/performance', '/ingestion', '/trends']

function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ||
    (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'))
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('theme', theme) } catch { /* storage unavailable */ }
  }, [theme])
  return (
    <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle colour theme"
      className="rounded-lg border border-line p-2 text-ink-2 hover:bg-surface-2">
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  )
}

function Sidebar({ onNavigate }) {
  const health = useApi('/api/health')
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white"><BarChart3 size={18} /></div>
        <div>
          <p className="text-sm font-semibold leading-tight text-ink">Pulse Analytics</p>
          <p className="text-[11px] leading-tight text-muted">Social media big data</p>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-2" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={{ pathname: to }} end={end} onClick={onNavigate}
            className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
              isActive ? 'bg-accent-soft font-medium text-accent' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'}`}>
            <Icon size={16} aria-hidden /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-lg border border-line p-3 text-xs">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${health.data?.mongodb ? 'bg-good' : health.loading ? 'bg-warn' : 'bg-critical'}`} aria-hidden />
          <span className="font-medium text-ink">{health.data?.mongodb ? 'MongoDB connected' : health.loading ? 'Connecting…' : 'Database offline'}</span>
        </div>
        {health.data?.posts !== undefined && (
          <p className="mt-1 text-muted">{fmtCompact(health.data.posts)} posts · MongoDB {health.data.server_version}</p>
        )}
      </div>
    </div>
  )
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const showFilters = !NO_FILTERS.includes(pathname)
  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 border-r border-line bg-surface lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-surface">
            <button className="absolute right-3 top-5 text-muted" aria-label="Close menu" onClick={() => setOpen(false)}><X size={18} /></button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-page/90 backdrop-blur">
          <div className="flex items-center gap-2 px-4 py-2.5 lg:px-6">
            <button className="rounded-lg border border-line p-2 text-ink-2 lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu size={16} /></button>
            <div className="min-w-0 flex-1">{showFilters ? <FilterBar /> : <span className="text-sm text-muted">Global filters are not used on this page</span>}</div>
            <ThemeToggle />
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 lg:px-6">
          <div className="mx-auto max-w-[1400px]"><Suspense fallback={<Skeleton height={480} />}><Outlet /></Suspense></div>
        </main>
      </div>
    </div>
  )
}
