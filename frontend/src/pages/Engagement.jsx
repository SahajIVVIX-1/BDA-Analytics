import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, KpiCard, PageHeader, Segmented, SentimentPill, SourceBadge, SyntheticBadge } from '../components/ui'
import { ChartTooltip, SENTIMENT_COLORS, axisProps, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtDateTime, fmtDay, fmtInt, tickForGranularity } from '../utils/format'

export default function Engagement() {
  const { filters } = useFilters()
  const [granularity, setGranularity] = useState('week')
  const en = useApi('/api/analytics/engagement', { ...filters, granularity, top: 10 })
  const t = en.data?.totals

  return (
    <>
      <PageHeader title="Engagement" description="Likes, comments and shares per post (engagement = likes + comments + shares) and the rate per 1,000 followers reached.">
        <div className="flex items-center gap-2"><SyntheticBadge /><SourceBadge meta={en.data?.meta} /></div>
      </PageHeader>

      <div role="note" className="mb-4 rounded-xl border border-synthetic/30 bg-synthetic-bg px-4 py-3 text-sm text-synthetic">
        <strong>These engagement numbers are synthetic.</strong> The FiveThirtyEight dataset has no likes, replies or retweet counts, so the
        project generates them from each author's real follower count (scripts/synthesize_engagement.py). They are here to show the
        analytics pipeline working end to end. They say nothing about how real audiences reacted, and differences between topics or
        sentiments only reflect differences in follower counts.
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KpiCard label="Total engagement" loading={!t} value={fmtCompact(t?.engagement)} />
        <KpiCard label="Likes" loading={!t} value={fmtCompact(t?.likes)} />
        <KpiCard label="Comments" loading={!t} value={fmtCompact(t?.comments)} />
        <KpiCard label="Shares" loading={!t} value={fmtCompact(t?.shares)} />
        <KpiCard label="Per 1k reach" loading={!t} value={t?.engagement_per_1k_reach?.toFixed(2)} hint="engagement / followers × 1000" />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Engagement over time" subtitle="Average engagement per post"
          actions={<Segmented label="Granularity" value={granularity} onChange={setGranularity} options={['day', 'week', 'month']} />}>
          <Async state={en} height={280} isEmpty={(x) => !x.over_time.length}>
            {(x) => (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={x.over_time} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="t" tickFormatter={tickForGranularity(granularity)} {...axisProps} minTickGap={40} />
                  <YAxis {...axisProps} width={40} />
                  <Tooltip content={<ChartTooltip labelFormatter={fmtDay} valueFormatter={(v) => v.toFixed(2)} />} />
                  <Line dataKey="avg_engagement" name="Avg engagement / post" stroke="var(--s1)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Async>
        </Card>
        <Card title="By sentiment" subtitle="Average engagement per post">
          <Async state={en} height={280} isEmpty={(x) => !x.by_sentiment.length}>
            {(x) => {
              const rows = ['positive', 'neutral', 'negative', 'not_analyzed'].map((k) => x.by_sentiment.find((r) => r.key === k)).filter(Boolean)
              return (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="key" {...axisProps} tickFormatter={(v) => v.replace('_', ' ')} />
                    <YAxis {...axisProps} width={36} />
                    <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v, p) => `${v.toFixed(2)} (n=${fmtInt(p.payload.posts)})`} />} />
                    <Bar dataKey="avg_engagement" name="Avg engagement" radius={[4, 4, 0, 0]} barSize={40} isAnimationActive={false}>
                      {rows.map((r) => <Cell key={r.key} fill={SENTIMENT_COLORS[r.key]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )
            }}
          </Async>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="By topic" subtitle="Top 12 assigned topics by total engagement (unassigned posts excluded)">
          <Async state={en} height={360} isEmpty={(x) => !x.by_topic.length}>
            {(x) => (
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={x.by_topic.filter((r) => r.key !== 'none' && !r.key.endsWith('-other')).slice(0, 12).map((r) => ({ ...r, label: `${r.key.slice(0, 2)} · ${r.label}` }))} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid {...gridProps} horizontal={false} vertical />
                  <XAxis type="number" tickFormatter={fmtCompact} {...axisProps} />
                  <YAxis type="category" dataKey="label" {...axisProps} width={150} tickFormatter={(v) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)} />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
                  <Bar dataKey="engagement" name="Engagement" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Async>
        </Card>
        <Card title="Top posts" subtitle="Highest engagement (walks the engagement.total index)">
          <Async state={en} height={360} isEmpty={(x) => !x.top_posts.length}>
            {(x) => (
              <ol className="space-y-3">
                {x.top_posts.map((p) => (
                  <li key={p.id} className="border-b border-line pb-3 last:border-0">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                      <span className="font-medium text-ink-2">@{p.user?.username}</span>
                      <span>{fmtDateTime(p.created_at)}</span>
                      <SentimentPill label={p.sentiment?.label} />
                      <span className="ml-auto font-medium tabular text-ink">{fmtInt(p.engagement?.total)}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm text-ink">{p.text}</p>
                  </li>
                ))}
              </ol>
            )}
          </Async>
        </Card>
      </div>
    </>
  )
}
