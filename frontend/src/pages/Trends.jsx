import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, Note, PageHeader, Segmented, SourceBadge, Table } from '../components/ui'
import { ChartTooltip, Legend, axisProps, colorMap, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilterOptions } from '../components/FilterBar'
import { fmtCompact, fmtDay, fmtInt, fmtSigned, langName } from '../utils/format'

const sel = 'h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink'

export default function Trends() {
  const [kind, setKind] = useState('hashtag')
  const [windowDays, setWindowDays] = useState(7)
  const [end, setEnd] = useState('2016-11-08')
  const [language, setLanguage] = useState('en')
  const opts = useFilterOptions().data
  const minCount = kind === 'topic' ? 1 : kind === 'keyword' ? 30 : 20
  const tr = useApi('/api/analytics/trends', { kind, window_days: windowDays, end, limit: 25, min_count: minCount,
    language: kind === 'hashtag' ? undefined : language })
  const top = useApi('/api/analytics/hashtags', { start: undefined, limit: 20 })

  const presets = [
    ['2016-11-08', 'US election day 2016'], ['2016-07-28', 'DNC convention 2016'], ['2017-08-15', 'Charlottesville, Aug 2017'],
    ['2015-11-20', 'Paris attacks, Nov 2015'], [opts?.date_range?.last?.slice(0, 10) || '2018-05-30', 'End of dataset'],
  ]

  return (
    <>
      <PageHeader title="Trends" description="What grew fastest in a window compared with the window just before it. Pick an end date to replay any moment in the dataset.">
        <SourceBadge meta={tr.data?.meta && { ...tr.data.meta, source: tr.data.meta.source }} />
      </PageHeader>

      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented label="Trend type" value={kind} onChange={setKind} options={[{ value: 'hashtag', label: 'Hashtags' }, { value: 'keyword', label: 'Keywords' }, { value: 'topic', label: 'Topics' }]} />
          <Segmented label="Window" value={windowDays} onChange={setWindowDays} options={[{ value: 1, label: '1 day' }, { value: 7, label: '7 days' }, { value: 30, label: '30 days' }]} />
          <label className="flex items-center gap-2 text-xs text-muted">Window ends
            <input type="date" className={sel} value={end} onChange={(e) => setEnd(e.target.value)}
              min={opts?.date_range?.first?.slice(0, 10)} max={opts?.date_range?.last?.slice(0, 10)} />
          </label>
          <select aria-label="Jump to event" className={sel} value="" onChange={(e) => e.target.value && setEnd(e.target.value)}>
            <option value="">Jump to…</option>
            {presets.map(([d, l]) => <option key={l} value={d}>{l}</option>)}
          </select>
          {kind !== 'hashtag' && (
            <Segmented label="Language" value={language} onChange={setLanguage} options={[{ value: 'en', label: 'English' }, { value: 'ru', label: 'Russian' }]} />
          )}
        </div>
      </Card>

      <div className="mt-4 grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3" title={`Top trending ${kind}s`}
          subtitle={tr.data?.window && `${fmtDay(tr.data.window.current[0])} – ${fmtDay(new Date(new Date(tr.data.window.current[1]) - 1).toISOString())} vs the ${windowDays} day${windowDays > 1 ? 's' : ''} before`}>
          {tr.data?.warning && <div role="note" className="mb-3 rounded-lg bg-synthetic-bg px-3 py-2 text-xs text-synthetic">{tr.data.warning}</div>}
          <Async state={tr} height={420} isEmpty={(x) => !x.items.length}>
            {(x) => (
              <Table dense rowKey={(r) => r.key} rows={x.items} columns={[
                { key: 'rank', label: '#', render: (r) => <span className="text-muted tabular">{x.items.indexOf(r) + 1}</span> },
                { key: 'label', label: kind[0].toUpperCase() + kind.slice(1), render: (r) => (
                  <Link className="font-medium text-ink hover:text-accent"
                    to={kind === 'hashtag' ? `/explorer?hashtag=${encodeURIComponent(r.key)}` : kind === 'topic' ? `/explorer?topic=${r.key}` : `/explorer?q=${encodeURIComponent(r.key)}`}>
                    {kind === 'hashtag' ? `#${r.key}` : r.label}
                  </Link>) },
                { key: 'current', label: 'Now', align: 'right', render: (r) => fmtInt(r.current) },
                { key: 'previous', label: 'Before', align: 'right', render: (r) => fmtInt(r.previous) },
                { key: 'growth_pct', label: 'Growth', align: 'right', render: (r) => <span className={r.growth_pct >= 0 ? 'text-good' : 'text-critical'}>{fmtSigned(r.growth_pct, 0)}%</span> },
                { key: 'share_growth_pct', label: 'Share growth', align: 'right', render: (r) => r.share_growth_pct === null ? '–' : <span className={r.share_growth_pct >= 0 ? 'text-good' : 'text-critical'}>{fmtSigned(r.share_growth_pct, 0)}%</span> },
                { key: 'trend_score', label: 'Score', align: 'right', render: (r) => r.trend_score.toFixed(2) },
                { key: 'avg_reach', label: 'Avg reach', align: 'right', render: (r) => fmtCompact(r.avg_reach) },
              ]} />
            )}
          </Async>
          <div className="mt-3"><Note>Trend score = log10(1 + now) × log2((now + 5) / (before + 5)) × (1 + 0.1 · log10(1 + avg reach)). The +5 smoothing stops tiny counts (0 → 3) looking like infinite growth. Share growth = change in the item's share of all posts, which corrects for changes in overall data volume.</Note></div>
        </Card>

        <Card className="xl:col-span-2" title="Daily timeline of the top 5" subtitle="Context: the 8 windows leading up to the end date">
          <Async state={tr} height={300} isEmpty={(x) => !x.timeline?.series?.length}>
            {(x) => {
              const keys = x.items.slice(0, 5).map((i) => i.key)
              const colors = colorMap(keys)
              const label = (k) => (kind === 'hashtag' ? `#${k}` : x.items.find((i) => i.key === k)?.label || k)
              return (
                <>
                  <ResponsiveContainer width="100%" height={280}>
                    <LineChart data={x.timeline.series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="t" tickFormatter={(v) => fmtDay(v).replace(/, \d{4}/, '')} {...axisProps} minTickGap={30} />
                      <YAxis tickFormatter={fmtCompact} {...axisProps} width={40} />
                      <Tooltip content={<ChartTooltip labelFormatter={fmtDay} nameFormatter={label} />} />
                      {keys.map((k) => <Line key={k} dataKey={k} name={k} stroke={colors[k]} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />)}
                    </LineChart>
                  </ResponsiveContainer>
                  <Legend items={keys.map((k) => ({ key: k, label: label(k), color: colors[k] }))} />
                </>
              )
            }}
          </Async>
        </Card>
      </div>

      <Card className="mt-4" title="Most used hashtags, all time" subtitle="From the hashtag_daily rollup ($unwind + $group in MongoDB)" badges={<SourceBadge meta={top.data?.meta} />}>
        <Async state={top} height={320} isEmpty={(x) => !x.items.length}>
          {(x) => (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={x.items} margin={{ top: 8, right: 8, left: 0, bottom: 40 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="hashtag" {...axisProps} interval={0} angle={-35} textAnchor="end" tickFormatter={(v) => `#${v}`} height={50} />
                <YAxis tickFormatter={fmtCompact} {...axisProps} width={44} />
                <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip labelFormatter={(v) => `#${v}`} />} />
                <Bar dataKey="posts" name="Posts" fill="var(--s1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Async>
      </Card>
      <p className="mt-2 text-xs text-muted">Keyword trends use per-post TF-IDF keywords; topic trends use the NMF topic assignment. Language: {langName(language)}.</p>
    </>
  )
}
