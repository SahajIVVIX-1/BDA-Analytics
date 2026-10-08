import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, Note, PageHeader, Segmented, SourceBadge, SyntheticBadge, Table } from '../components/ui'
import { ChartTooltip, Legend, SentimentBar, axisProps, colorMap, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtDay, fmtInt, fmtPct, fmtSigned, tickForGranularity } from '../utils/format'

export default function Topics() {
  const { filters } = useFilters()
  const [granularity, setGranularity] = useState('month')
  const [lang, setLang] = useState('en')
  const params = { ...filters, language: filters.language || lang, granularity, top: 8 }
  const tp = useApi('/api/analytics/topics', params)
  const [selected, setSelected] = useState(null)

  const timelineKeys = tp.data?.timeline_keys
  const keys = useMemo(() => timelineKeys || [], [timelineKeys])
  const colors = useMemo(() => colorMap(keys), [keys])

  return (
    <>
      <PageHeader title="Topics" description="Topics are discovered with TF-IDF + NMF (non-negative matrix factorisation), one model per language. Labels are the topic's top terms.">
        <div className="flex items-center gap-2">
          {!filters.language && <Segmented label="Language" value={lang} onChange={setLang} options={[{ value: 'en', label: 'English' }, { value: 'ru', label: 'Russian' }]} />}
          <SourceBadge meta={tp.data?.meta} />
        </div>
      </PageHeader>

      <Card title="Topic popularity over time" subtitle="Posts per period for the 8 largest topics"
        actions={<Segmented label="Granularity" value={granularity} onChange={setGranularity} options={['week', 'month']} />}>
        <Async state={tp} height={320} isEmpty={(x) => !x.timeline.length}>
          {(x) => (
            <>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={x.timeline} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="t" tickFormatter={tickForGranularity(granularity)} {...axisProps} minTickGap={40} />
                  <YAxis tickFormatter={fmtCompact} {...axisProps} width={44} />
                  <Tooltip content={<ChartTooltip labelFormatter={fmtDay} nameFormatter={(k) => x.labels[k] || k} />} />
                  {keys.map((k) => <Area key={k} dataKey={k} name={k} stackId="1" stroke={colors[k]} fill={colors[k]} fillOpacity={0.8} strokeWidth={1} isAnimationActive={false} />)}
                </AreaChart>
              </ResponsiveContainer>
              <Legend items={keys.map((k) => ({ key: k, label: x.labels[k], color: colors[k] }))} />
            </>
          )}
        </Async>
      </Card>

      <Card className="mt-4" title="All topics" subtitle="Click a row to see its top terms. Growth compares the last 30 days of the selected range (or of the main activity period) with the 30 days before. Avg engagement is synthetic."
        badges={tp.data && <SyntheticBadge />}>
        {tp.data?.growth_warning && <div role="note" className="mb-3 rounded-lg bg-synthetic-bg px-3 py-2 text-xs text-synthetic">{tp.data.growth_warning}</div>}
        <Async state={tp} height={400} isEmpty={(x) => !x.topics.length}>
          {(x) => (
            <Table rowKey={(r) => r.topic_id} rows={x.topics} onRowClick={(r) => setSelected(r.topic_id === selected ? null : r.topic_id)} columns={[
              { key: 'label', label: 'Topic', render: (r) => (
                <div className="min-w-48">
                  <span className="font-medium text-ink">{r.label}</span>
                  {selected === r.topic_id && r.top_terms.length > 0 && <p className="mt-1 text-xs text-muted">{r.top_terms.join(' · ')}</p>}
                </div>) },
              { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtInt(r.posts) },
              { key: 'share_pct', label: 'Share', align: 'right', render: (r) => fmtPct(r.share_pct) },
              { key: 'growth_pct', label: 'Growth (30d)', align: 'right', render: (r) => r.growth_pct === null ? '–' : <span className={r.growth_pct >= 0 ? 'text-good' : 'text-critical'}>{fmtSigned(r.growth_pct, 0)}%</span> },
              { key: 'share_growth_pct', label: 'Share growth', align: 'right', render: (r) => r.share_growth_pct == null ? '–' : <span className={r.share_growth_pct >= 0 ? 'text-good' : 'text-critical'}>{fmtSigned(r.share_growth_pct, 0)}%</span> },
              { key: 'sentiment', label: 'Sentiment mix', render: (r) => r.language === 'en' ? <div className="w-32 pt-1.5"><SentimentBar {...r.sentiment} /></div> : <span className="text-xs text-muted">not modelled</span> },
              { key: 'net', label: 'Net', align: 'right', render: (r) => r.net_sentiment === null ? '–' : fmtSigned(100 * r.net_sentiment, 0) },
              { key: 'avg_engagement', label: 'Avg engagement', align: 'right', render: (r) => r.avg_engagement.toFixed(1) },
              { key: 'reach', label: 'Reach', align: 'right', render: (r) => fmtCompact(r.reach) },
              { key: 'go', label: '', render: (r) => <Link onClick={(e) => e.stopPropagation()} className="text-xs text-accent hover:underline" to={`/explorer?topic=${r.topic_id}`}>Posts</Link> },
            ]} />
          )}
        </Async>
        <div className="mt-3"><Note>"Other / unassigned" holds posts whose strongest topic weight is below 0.02 (too little modelled vocabulary to place them). Avg engagement is synthetic.</Note></div>
      </Card>
    </>
  )
}
