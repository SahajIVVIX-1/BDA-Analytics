import { fmtInt } from '../utils/format'

export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)']
export const SENTIMENT_COLORS = { positive: 'var(--pos)', neutral: 'var(--neu)', negative: 'var(--neg)', not_analyzed: 'var(--grid)' }
export const SENTIMENTS = ['positive', 'neutral', 'negative']

// Colour follows the entity, not its rank: a key keeps its slot as long as the stable key list is the same.
export function colorMap(keys) {
  const m = {}
  keys.forEach((k, i) => { m[k] = i < SERIES.length ? SERIES[i] : 'var(--ink-muted)' })
  return m
}

export function ChartTooltip({ active, payload, label, labelFormatter, valueFormatter = fmtInt, nameFormatter = (n) => n }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      {label !== undefined && <p className="mb-1 font-medium text-ink">{labelFormatter ? labelFormatter(label) : label}</p>}
      <ul className="space-y-0.5">
        {payload.filter((p) => p.value !== undefined && p.value !== null).map((p) => (
          <li key={p.dataKey ?? p.name} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-ink-2">
              <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} aria-hidden />
              {nameFormatter(p.name)}
            </span>
            <span className="tabular font-medium text-ink">{valueFormatter(p.value, p)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export const axisProps = { tickLine: false, axisLine: false, fontSize: 11 }
export const gridProps = { strokeDasharray: '0', vertical: false }

// Horizontal stacked 100% bar used for sentiment mixes.
export function SentimentBar({ positive = 0, neutral = 0, negative = 0, height = 8 }) {
  const n = positive + neutral + negative
  if (!n) return <div className="h-2 rounded bg-surface-2" />
  return (
    <div className="flex w-full gap-[2px] overflow-hidden rounded" style={{ height }} role="img"
      aria-label={`positive ${Math.round((100 * positive) / n)}%, neutral ${Math.round((100 * neutral) / n)}%, negative ${Math.round((100 * negative) / n)}%`}>
      {[['positive', positive], ['neutral', neutral], ['negative', negative]].map(([k, v]) => v > 0 && (
        <div key={k} title={`${k}: ${fmtInt(v)} (${((100 * v) / n).toFixed(1)}%)`} style={{ width: `${(100 * v) / n}%`, background: SENTIMENT_COLORS[k] }} />
      ))}
    </div>
  )
}

export function Legend({ items }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} aria-hidden /> {i.label}
        </li>
      ))}
    </ul>
  )
}
