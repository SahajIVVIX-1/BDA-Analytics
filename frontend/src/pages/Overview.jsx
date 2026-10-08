import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FileText, Hash, Layers, Megaphone, Smile, Frown, Meh, Zap } from 'lucide-react'
import { Async, Card, KpiCard, Note, PageHeader, Segmented, SourceBadge, SyntheticBadge } from '../components/ui'
import { ChartTooltip, SENTIMENT_COLORS, SentimentBar, axisProps, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtDay, fmtInt, fmtPct, fmtSigned, langName, tickForGranularity } from '../utils/format'

export default function Overview() {
  const { filters } = useFilters()
  const [granularity, setGranularity] = useState('week')
  const ov = useApi('/api/dashboard/overview', filters)
  const ts = useApi('/api/analytics/timeseries', { ...filters, granularity, split_by: 'sentiment' })
  const topics = useApi('/api/analytics/topics', { ...filters, top: 8 })
  const trends = useApi('/api/analytics/trends', { kind: 'hashtag', end: filters.end, window_days: 7, limit: 8, timeline: false })
  const langs = useApi('/api/analytics/languages', filters)
  const d = ov.data
  const s = d?.sentiment

  return (
    <>
      <PageHeader title="Overview"
        description="2.9 million real tweets from FiveThirtyEight's Internet Research Agency dataset, stored and analysed in MongoDB.">
        <SourceBadge meta={d?.meta} />
      </PageHeader>

      {ov.error ? <Card><Async state={ov}>{() => null}</Async></Card> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          <KpiCard label="Total posts" icon={FileText} loading={!d} value={fmtCompact(d?.total_posts)} hint={d && `${fmtInt(d.total_posts)} documents`} />
          <KpiCard label="Positive" icon={Smile} loading={!d} value={fmtPct(s?.percent.positive)} hint="of English posts analysed" />
          <KpiCard label="Neutral" icon={Meh} loading={!d} value={fmtPct(s?.percent.neutral)} hint={d && `${fmtCompact(s.analysed)} analysed`} />
          <KpiCard label="Negative" icon={Frown} loading={!d} value={fmtPct(s?.percent.negative)} hint={d && `avg score ${fmtSigned(d.avg_sentiment_score, 3)}`} />
          <KpiCard label="Engagement" icon={Zap} loading={!d} value={fmtCompact(d?.engagement.total)}
            hint={d?.engagement.synthetic ? <SyntheticBadge /> : 'likes + comments + shares'} />
          <KpiCard label="Audience reach" icon={Megaphone} loading={!d} value={fmtCompact(d?.total_reach)} hint="sum of author followers" />
          <KpiCard label="Topics" icon={Layers} loading={!d} value={d?.topics} hint="NMF topics (en + ru)" />
          <KpiCard label="Trending hashtags" icon={Hash} loading={!d} value={d?.trending_hashtags} hint="growing, last 7 days" />
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Posting volume by sentiment" subtitle="Stacked: English posts by predicted sentiment. Dashed: every post, any language."
          badges={<SourceBadge meta={ts.data?.meta} />}
          actions={<Segmented label="Granularity" value={granularity} onChange={setGranularity} options={['day', 'week', 'month']} />}>
          <Async state={ts} height={300} isEmpty={(x) => !x.series.length}>
            {(x) => (
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={x.series.map((p) => ({ ...p, total: (p.positive || 0) + (p.neutral || 0) + (p.negative || 0) + (p.not_analyzed || 0) }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="t" tickFormatter={tickForGranularity(granularity)} {...axisProps} minTickGap={40} />
                  <YAxis tickFormatter={fmtCompact} {...axisProps} width={44} />
                  <Tooltip content={<ChartTooltip labelFormatter={fmtDay} nameFormatter={(n) => n.replace('_', ' ')} />} />
                  {['negative', 'neutral', 'positive'].map((k) => (
                    <Area key={k} type="monotone" dataKey={k} name={k} stackId="1" stroke={SENTIMENT_COLORS[k]} strokeWidth={1}
                      fill={SENTIMENT_COLORS[k]} fillOpacity={0.85} isAnimationActive={false} />
                  ))}
                  <Line type="monotone" dataKey="total" name="all posts (all languages)" stroke="var(--ink-2)" strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </Async>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-2">
            {['positive', 'neutral', 'negative'].map((k) => (
              <span key={k} className="flex items-center gap-1.5 capitalize"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SENTIMENT_COLORS[k] }} />{k} (English)</span>
            ))}
            <span className="flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-dashed border-ink-2" />All posts, all languages</span>
          </div>
        </Card>

        <Card title="Trending hashtags" subtitle={trends.data?.window ? `7 days to ${fmtDay(new Date(new Date(trends.data.window.current[1]) - 1).toISOString())} vs the 7 before (end of main activity period)` : 'Window-over-window growth'}
          actions={<Link to="/trends" className="text-xs text-accent hover:underline">All trends</Link>}>
          <Async state={trends} height={300} isEmpty={(x) => !x.items.length}>
            {(x) => (
              <>
              {x.warning && <p className="mb-3 rounded-lg bg-synthetic-bg px-3 py-2 text-xs text-synthetic">Overall volume changed {fmtInt(x.totals.previous)} → {fmtInt(x.totals.current)} posts between windows; growth shown is share growth.</p>}
              <ol className="space-y-2">
                {x.items.map((t, i) => (
                  <li key={t.key} className="flex items-center gap-3 text-sm">
                    <span className="w-5 text-right text-xs text-muted tabular">{i + 1}</span>
                    <Link to={`/explorer?hashtag=${encodeURIComponent(t.key)}`} className="min-w-0 flex-1 truncate font-medium text-ink hover:text-accent">#{t.key}</Link>
                    <span className="tabular text-xs text-ink-2">{fmtInt(t.current)}</span>
                    <span className={`w-16 text-right tabular text-xs font-medium ${(x.warning ? t.share_growth_pct : t.growth_pct) >= 0 ? 'text-good' : 'text-critical'}`}>{fmtSigned(x.warning ? t.share_growth_pct : t.growth_pct, 0)}%</span>
                  </li>
                ))}
              </ol>
              </>
            )}
          </Async>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" title="Top topics" subtitle="Posts per topic with sentiment mix (English topics have sentiment)"
          actions={<Link to="/topics" className="text-xs text-accent hover:underline">Topic analysis</Link>}>
          <Async state={topics} height={280} isEmpty={(x) => !x.topics.length}>
            {(x) => {
              const rows = x.topics.filter((t) => !t.topic_id.endsWith('-other')).slice(0, 10)
              const max = Math.max(...rows.map((r) => r.posts))
              return (
                <ul className="space-y-2.5">
                  {rows.map((t) => (
                    <li key={t.topic_id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[14rem_minmax(0,1fr)_5rem]">
                      <Link to={`/explorer?topic=${t.topic_id}`} className="truncate text-sm text-ink hover:text-accent" title={t.top_terms.join(', ')}>
                        <span className="mr-1 text-[10px] uppercase text-muted">{t.language}</span>{t.label}
                      </Link>
                      <div className="order-3 col-span-2 sm:order-none sm:col-span-1">
                        <div className="h-2 rounded bg-surface-2"><div className="h-2 rounded bg-[var(--s1)]" style={{ width: `${(100 * t.posts) / max}%` }} /></div>
                        {t.language === 'en' && <div className="mt-1"><SentimentBar {...t.sentiment} height={4} /></div>}
                      </div>
                      <span className="text-right text-xs tabular text-ink-2">{fmtCompact(t.posts)}</span>
                    </li>
                  ))}
                </ul>
              )
            }}
          </Async>
        </Card>
        <Card title="Languages" subtitle="Share of posts">
          <Async state={langs} height={280} isEmpty={(x) => !x.languages.length}>
            {(x) => (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={x.languages.slice(0, 8)} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid {...gridProps} horizontal={false} vertical />
                  <XAxis type="number" tickFormatter={fmtCompact} {...axisProps} />
                  <YAxis type="category" dataKey="language" tickFormatter={langName} {...axisProps} width={72} />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip labelFormatter={langName} />} />
                  <Bar dataKey="posts" name="Posts" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Async>
          {s && <Note>Sentiment is modelled for English only ({fmtCompact(s.analysed)} posts); topics for English and Russian.</Note>}
        </Card>
      </div>
    </>
  )
}
