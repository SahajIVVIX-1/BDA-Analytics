import { EmptyState, Segmented, useTab } from '../../components/ui'
import { fmtDateTime } from '../../utils/format'

// Sub-views inside a tab: a segmented control instead of stacking everything into one long page.
export function useView(views) {
  return useTab(views.map((v) => v.id), 'view')
}

export function ViewSwitch({ views, value, onChange }) {
  return (
    <div className="mb-4 overflow-x-auto">
      <Segmented label="View" keepCase value={value} onChange={onChange}
        options={views.map((v) => ({ value: v.id, label: v.label }))} />
    </div>
  )
}

export function RunInfo({ r }) {
  if (!r?.hardware) return null
  const hw = r.hardware
  return (
    <p className="mt-3 text-xs text-muted">
      Measured {fmtDateTime(r.run_at)} on {hw.label}: {hw.cpu_count} CPUs{hw.ram_gb ? `, ${hw.ram_gb} GB RAM` : ''}
      {hw.spark ? `, Spark ${hw.spark}` : ''}{hw.java ? ` (Java ${hw.java})` : ''}{hw.mongodb ? `, MongoDB ${hw.mongodb}` : ''}, Python {hw.python}.
    </p>
  )
}

export function NotRun({ cmd }) {
  return <EmptyState title="Not measured yet" hint={`Run: ${cmd}`} />
}

export function Code({ children }) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-lg border border-line bg-surface-2 p-3 text-[11px] leading-relaxed text-ink-2">
      {children}
    </pre>
  )
}

export function Stat({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 whitespace-nowrap text-lg font-semibold text-ink tabular">{value}</p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  )
}

export const sec = (v) => (v === null || v === undefined ? '–' : `${Number(v).toFixed(v < 10 ? 2 : 1)} s`)
