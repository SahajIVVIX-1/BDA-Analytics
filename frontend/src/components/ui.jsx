import { AlertTriangle, Database, FlaskConical, Inbox, Info, RefreshCw } from 'lucide-react'
import { fmtMs } from '../utils/format'

export function Card({ title, subtitle, actions, children, className = '', badges, bodyClass = '' }) {
  return (
    <section className={`rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.04)] ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-2 px-4 pt-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-ink">{title}</h2>
              {badges}
            </div>
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`p-4 ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function KpiCard({ label, value, hint, icon: Icon, tone, loading }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
        {Icon && <Icon size={16} className="text-muted" aria-hidden />}
      </div>
      {loading ? (
        <div className="skeleton mt-3 h-8 w-24" />
      ) : (
        <p className="mt-2 text-2xl font-semibold text-ink" style={tone ? { color: tone } : undefined}>{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function Skeleton({ height = 240 }) {
  return <div className="skeleton w-full" style={{ height }} aria-busy="true" aria-label="Loading" />
}

export function ErrorState({ error, onRetry }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <AlertTriangle className="text-critical" size={22} aria-hidden />
      <p className="text-sm font-medium text-ink">Could not load this data</p>
      <p className="max-w-md text-xs text-muted">{error?.message || String(error)}</p>
      {onRetry && (
        <button onClick={onRetry} className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-xs text-ink-2 hover:bg-surface-2">
          <RefreshCw size={12} /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title = 'No data for these filters', hint = 'Try widening the date range or clearing filters.' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 py-10 text-center">
      <Inbox className="text-muted" size={22} aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="max-w-sm text-xs text-muted">{hint}</p>
    </div>
  )
}

// Renders loading / error / empty states around content.
export function Async({ state, height = 240, isEmpty, children }) {
  if (state.loading && !state.data) return <Skeleton height={height} />
  if (state.error) return <ErrorState error={state.error} onRetry={state.retry} />
  if (!state.data) return null
  if (isEmpty && isEmpty(state.data)) return <EmptyState />
  return <div className={state.loading ? 'opacity-60 transition-opacity' : ''}>{children(state.data)}</div>
}

export function SyntheticBadge({ title = 'Engagement counts are synthetic: the source dataset has no likes, replies or retweet counts. Values depend only on follower counts.' }) {
  return (
    <span title={title} className="inline-flex items-center gap-1 rounded-full bg-synthetic-bg px-2 py-0.5 text-[11px] font-medium text-synthetic">
      <FlaskConical size={11} aria-hidden /> Synthetic data
    </span>
  )
}

export function SourceBadge({ meta }) {
  if (!meta) return null
  const label = meta.source === 'cube' ? 'pre-aggregated cube' : meta.source
  return (
    <span title="MongoDB collection that answered this query, and server time" className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">
      <Database size={11} aria-hidden /> {label} · {fmtMs(meta.query_ms)}
    </span>
  )
}

export function Note({ children }) {
  return (
    <p className="flex items-start gap-1.5 text-xs text-muted">
      <Info size={13} className="mt-0.5 shrink-0" aria-hidden /> <span>{children}</span>
    </p>
  )
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o) => {
        const v = typeof o === 'string' ? o : o.value
        const l = typeof o === 'string' ? o : o.label
        const active = v === value
        return (
          <button key={v} role="radio" aria-checked={active} onClick={() => onChange(v)}
            className={`rounded-md px-2.5 py-1 text-xs capitalize transition-colors ${active ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'}`}>
            {l}
          </button>
        )
      })}
    </div>
  )
}

export function PageHeader({ title, description, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function SentimentPill({ label }) {
  if (!label) return <span className="text-xs text-muted">n/a</span>
  const color = { positive: 'var(--pos)', neutral: 'var(--neu)', negative: 'var(--neg)' }[label]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs capitalize text-ink-2">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden /> {label}
    </span>
  )
}

export function Table({ columns, rows, rowKey, onRowClick, dense }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            {columns.map((c) => (
              <th key={c.key} className={`px-2 py-2 font-medium ${c.align === 'right' ? 'text-right' : ''}`}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r) : i} onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={`border-b border-line last:border-0 ${onRowClick ? 'cursor-pointer hover:bg-surface-2' : ''}`}>
              {columns.map((c) => (
                <td key={c.key} className={`px-2 ${dense ? 'py-1.5' : 'py-2.5'} align-top text-ink-2 ${c.align === 'right' ? 'text-right tabular' : ''}`}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
