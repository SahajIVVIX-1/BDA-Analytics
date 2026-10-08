import { useEffect, useState } from 'react'
import { SlidersHorizontal, X } from 'lucide-react'
import { useFilters } from '../hooks/useFilters'
import { useApi } from '../hooks/useApi'
import { fmtCompact, langName } from '../utils/format'

const sel = 'h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-accent/40'

export function useFilterOptions() {
  return useApi('/api/meta/filters')
}

export default function FilterBar({ extended = false }) {
  const { filters, setFilter, setMany, clear, active } = useFilters()
  const opts = useFilterOptions().data
  const [hashtag, setHashtag] = useState(filters.hashtag || '')
  const [open, setOpen] = useState(false) // small screens: filters collapse behind a button
  useEffect(() => setHashtag(filters.hashtag || ''), [filters.hashtag])

  const minDay = opts?.date_range?.first?.slice(0, 10)
  const maxDay = opts?.date_range?.last?.slice(0, 10)

  const presets = [
    { label: 'All time', start: '', end: '' },
    { label: '2015', start: '2015-01-01', end: '2015-12-31' },
    { label: '2016', start: '2016-01-01', end: '2016-12-31' },
    { label: '2017', start: '2017-01-01', end: '2017-12-31' },
    { label: 'Election 2016', start: '2016-09-01', end: '2016-11-30' },
  ]

  return (
    <div>
    <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
      className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-xs text-ink sm:hidden">
      <SlidersHorizontal size={14} aria-hidden /> Filters{active > 0 ? ` (${active})` : ''}
    </button>
    <div className={`${open ? 'mt-2 flex' : 'hidden'} flex-wrap items-center gap-2 sm:mt-0 sm:flex`} role="group" aria-label="Filters">
      <SlidersHorizontal size={15} className="hidden text-muted sm:block" aria-hidden />
      <select aria-label="Date preset" className={sel}
        value={presets.find((p) => p.start === (filters.start || '') && p.end === (filters.end || ''))?.label || 'custom'}
        onChange={(e) => { const p = presets.find((x) => x.label === e.target.value); if (p) setMany({ start: p.start, end: p.end }) }}>
        {presets.map((p) => <option key={p.label}>{p.label}</option>)}
        <option value="custom" disabled>Custom range</option>
      </select>
      <input type="date" aria-label="Start date" className={sel} min={minDay} max={maxDay} value={filters.start || ''}
        onChange={(e) => setFilter('start', e.target.value)} />
      <span className="text-xs text-muted">–</span>
      <input type="date" aria-label="End date" className={sel} min={minDay} max={maxDay} value={filters.end || ''}
        onChange={(e) => setFilter('end', e.target.value)} />
      <select aria-label="Language" className={sel} value={filters.language || ''} onChange={(e) => setFilter('language', e.target.value)}>
        <option value="">All languages</option>
        {opts?.languages?.map((l) => <option key={l.value} value={l.value}>{langName(l.value)} ({fmtCompact(l.posts)})</option>)}
      </select>
      <select aria-label="Country" className={`${sel} max-w-40`} value={filters.country || ''} onChange={(e) => setFilter('country', e.target.value)}>
        <option value="">All countries</option>
        {opts?.countries?.map((c) => <option key={c.value} value={c.value}>{c.value} ({fmtCompact(c.posts)})</option>)}
      </select>
      <select aria-label="Sentiment" className={sel} value={filters.sentiment || ''} onChange={(e) => setFilter('sentiment', e.target.value)}>
        <option value="">All sentiment</option>
        {['positive', 'neutral', 'negative', 'not_analyzed'].map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
      </select>
      <select aria-label="Topic" className={`${sel} max-w-48`} value={filters.topic || ''} onChange={(e) => setFilter('topic', e.target.value)}>
        <option value="">All topics</option>
        {opts?.topics?.map((t) => <option key={t.value} value={t.value}>[{t.language}] {t.label}</option>)}
      </select>
      {extended && (
        <form onSubmit={(e) => { e.preventDefault(); setFilter('hashtag', hashtag.replace(/^#/, '')) }}>
          <input aria-label="Hashtag" placeholder="#hashtag" className={`${sel} w-28`} value={hashtag} onChange={(e) => setHashtag(e.target.value)}
            onBlur={() => setFilter('hashtag', hashtag.replace(/^#/, ''))} />
        </form>
      )}
      {active > 0 && (
        <button onClick={clear} className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-accent hover:bg-accent-soft">
          <X size={13} /> Clear ({active})
        </button>
      )}
    </div>
    </div>
  )
}
