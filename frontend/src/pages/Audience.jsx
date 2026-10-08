import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, EmptyState, Note, PageHeader, SourceBadge, Table } from '../components/ui'
import { ChartTooltip, SentimentBar, axisProps, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtInt, fmtPct, fmtSigned, langName } from '../utils/format'

export default function Audience() {
  const { filters } = useFilters()
  const geo = useApi('/api/analytics/geography', filters)
  const lang = useApi('/api/analytics/languages', filters)
  const users = useApi('/api/analytics/users', { limit: 15 })

  return (
    <>
      <PageHeader title="Geography & language" description="Where accounts were located (country-level region from the source data), which languages they posted in, and how account groups behaved.">
        <SourceBadge meta={geo.data?.meta} />
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Posts by country" subtitle={geo.data && `${fmtPct(geo.data.coverage_pct)} of posts have a known country`}>
          <Async state={geo} height={380} isEmpty={(x) => !x.countries.length}>
            {(x) => !x.available ? <EmptyState title="No location data" hint="This dataset has no usable location field, so the module is disabled." /> : (
              <ResponsiveContainer width="100%" height={380}>
                <BarChart data={x.countries.slice(0, 15)} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid {...gridProps} horizontal={false} vertical />
                  <XAxis type="number" scale="log" domain={[100, 'auto']} allowDataOverflow tickFormatter={fmtCompact} {...axisProps} />
                  <YAxis type="category" dataKey="country" {...axisProps} width={130} />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
                  <Bar dataKey="posts" name="Posts" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Async>
          <Note>Log scale: the United States dominates. {geo.data?.note}</Note>
        </Card>
        <Card title="Countries: sentiment and top topics">
          <Async state={geo} height={380} isEmpty={(x) => !x.countries.length}>
            {(x) => (
              <div className="max-h-[420px] overflow-y-auto">
                <Table dense rowKey={(r) => r.country} rows={x.countries.slice(0, 25)} columns={[
                  { key: 'country', label: 'Country', render: (r) => <span className="text-ink">{r.country}</span> },
                  { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtInt(r.posts) },
                  { key: 'sent', label: 'Sentiment (en)', render: (r) => <div className="w-24 pt-1.5"><SentimentBar {...r.sentiment} /></div> },
                  { key: 'net', label: 'Net', align: 'right', render: (r) => r.net_sentiment === null ? '–' : fmtSigned(100 * r.net_sentiment, 0) },
                  { key: 'top', label: 'Top topic', render: (r) => <span className="text-xs">{r.top_topics[0]?.label || '–'}</span> },
                ]} />
              </div>
            )}
          </Async>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Languages" subtitle={lang.data?.note} badges={<SourceBadge meta={lang.data?.meta} />}>
          <Async state={lang} height={360} isEmpty={(x) => !x.languages.length}>
            {(x) => (
              <div className="max-h-[400px] overflow-y-auto">
                <Table dense rowKey={(r) => r.language} rows={x.languages.slice(0, 20)} columns={[
                  { key: 'language', label: 'Language', render: (r) => <span className="text-ink">{langName(r.language)}</span> },
                  { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtInt(r.posts) },
                  { key: 'share_pct', label: 'Share', align: 'right', render: (r) => fmtPct(r.share_pct, 2) },
                  { key: 'top', label: 'Top topics', render: (r) => <span className="text-xs">{r.top_topics.slice(0, 2).map((t) => t.label).join('; ') || 'not modelled'}</span> },
                ]} />
              </div>
            )}
          </Async>
          {lang.data && <Note>Supported: sentiment in {lang.data.supported.sentiment.map(langName).join(', ')}; topics in {lang.data.supported.topics.map(langName).join(', ')}.</Note>}
        </Card>
        <Card title="Account categories" subtitle="Researcher-coded account themes (Linvill & Warren), from the users rollup" badges={<SourceBadge meta={users.data?.meta} />}>
          <Async state={users} height={360} isEmpty={(x) => !x.categories.length}>
            {(x) => (
              <Table dense rowKey={(r) => r.category} rows={x.categories} columns={[
                { key: 'category', label: 'Category', render: (r) => <span className="text-ink">{r.category}</span> },
                { key: 'accounts', label: 'Accounts', align: 'right', render: (r) => fmtInt(r.accounts) },
                { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtCompact(r.posts) },
                { key: 'rt', label: 'Retweet ratio', align: 'right', render: (r) => fmtPct(100 * r.avg_retweet_ratio, 0) },
                { key: 'ppd', label: 'Posts / active day', align: 'right', render: (r) => r.avg_posts_per_active_day.toFixed(1) },
                { key: 'net', label: 'Net sentiment', align: 'right', render: (r) => r.net_sentiment === null ? '–' : fmtSigned(100 * r.net_sentiment, 0) },
              ]} />
            )}
          </Async>
        </Card>
      </div>

      <Card className="mt-4" title="Most active accounts">
        <Async state={users} height={300} isEmpty={(x) => !x.top_users.length}>
          {(x) => (
            <Table dense rowKey={(r) => r.username} rows={x.top_users} columns={[
              { key: 'username', label: 'Account', render: (r) => <Link className="font-medium text-ink hover:text-accent" to={`/explorer?user=${encodeURIComponent(r.username)}`}>@{r.username}</Link> },
              { key: 'account_category', label: 'Category' },
              { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtInt(r.posts) },
              { key: 'active_days', label: 'Active days', align: 'right', render: (r) => fmtInt(r.active_days) },
              { key: 'ppd', label: 'Posts / day', align: 'right', render: (r) => r.posts_per_active_day },
              { key: 'max_followers', label: 'Max followers', align: 'right', render: (r) => fmtCompact(r.max_followers) },
              { key: 'rt', label: 'Retweets', align: 'right', render: (r) => fmtPct(100 * r.retweet_ratio, 0) },
              { key: 'lang', label: 'Languages', render: (r) => (r.languages || []).filter(Boolean).map(langName).join(', ') },
            ]} />
          )}
        </Async>
      </Card>
    </>
  )
}
