import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, Note, Table } from '../../components/ui'
import { ChartTooltip, Legend, axisProps, colorMap, gridProps } from '../../charts/common'
import { fmtCompact, fmtDay, fmtInt, langName } from '../../utils/format'
import { NotRun, RunInfo, Stat, ViewSwitch, useView } from './shared'

function Activity({ g }) {
  const cats = g.categories.map((c) => c.account_category || 'Unknown')
  const colors = colorMap(cats)
  const byMonth = {}
  g.monthly_category.forEach((x) => {
    const key = `${x.year}-${String(x.month).padStart(2, '0')}`
    byMonth[key] = byMonth[key] || { month: key }
    byMonth[key][x.account_category || 'Unknown'] = x.posts
  })
  const rows = Object.values(byMonth).sort((a, b) => a.month.localeCompare(b.month))
  const peak = [...g.monthly_total].sort((a, b) => b.posts - a.posts)[0]
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
      <Card title="Posts per month by account category" subtitle="gold/monthly_category, built by Spark from silver">
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="month" {...axisProps} interval={5} />
            <YAxis {...axisProps} width={48} tickFormatter={fmtCompact} />
            <Tooltip content={<ChartTooltip />} />
            {cats.map((c) => <Area key={c} dataKey={c} stackId="1" type="monotone" stroke={colors[c]} fill={colors[c]} fillOpacity={0.75} isAnimationActive={false} />)}
          </AreaChart>
        </ResponsiveContainer>
        <Legend items={cats.map((c) => ({ key: c, label: c, color: colors[c] }))} />
      </Card>
      <Card title="Gold tables" subtitle="Rows in each aggregate">
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(g.row_counts).map(([k, v]) => <Stat key={k} label={k.replaceAll('_', ' ')} value={fmtCompact(v)} />)}
        </div>
        <Note>Busiest month: {peak.year}-{String(peak.month).padStart(2, '0')} with {fmtInt(peak.posts)} posts.</Note>
      </Card>
    </div>
  )
}

function Hashtags({ g }) {
  const rows = g.top_hashtags.slice(0, 15)
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Top hashtags" subtitle="gold/top_hashtags (exploded from silver.hashtags)">
        <ResponsiveContainer width="100%" height={380}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, left: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} horizontal={false} vertical />
            <XAxis type="number" {...axisProps} tickFormatter={fmtCompact} />
            <YAxis type="category" dataKey="hashtag" {...axisProps} width={110} tickFormatter={(v) => `#${v}`} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
            <Bar dataKey="posts" name="Posts" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card title="Hashtag lifetimes" subtitle="First and last day seen, and the busiest day">
        <div className="max-h-[400px] overflow-y-auto">
          <Table dense rowKey={(x) => x.hashtag} rows={g.top_hashtags} columns={[
            { key: 'hashtag', label: 'Hashtag', render: (x) => <span className="text-ink">#{x.hashtag}</span> },
            { key: 'posts', label: 'Posts', align: 'right', render: (x) => fmtInt(x.posts) },
            { key: 'days', label: 'Days active', align: 'right', render: (x) => fmtInt(x.days_active) },
            { key: 'span', label: 'Seen', render: (x) => <span className="whitespace-nowrap text-xs">{fmtDay(x.first_seen)} → {fmtDay(x.last_seen)}</span> },
            { key: 'peak', label: 'Peak day', align: 'right', render: (x) => <span className="whitespace-nowrap text-xs">{fmtDay(x.peak_day)} ({fmtInt(x.peak_posts)})</span> },
          ]} />
        </div>
      </Card>
    </div>
  )
}

function Accounts({ g }) {
  return (
    <Card title="Most active accounts" subtitle="gold/account_stats: one row per account">
      <Table dense rowKey={(x) => x.username} rows={g.top_accounts} columns={[
        { key: 'username', label: 'Account', render: (x) => <span className="font-medium text-ink">@{x.username}</span> },
        { key: 'account_category', label: 'Category' },
        { key: 'posts', label: 'Posts', align: 'right', render: (x) => fmtInt(x.posts) },
        { key: 'rt', label: 'Retweets', align: 'right', render: (x) => `${Math.round(x.retweet_ratio * 100)}%` },
        { key: 'followers', label: 'Max followers', align: 'right', render: (x) => fmtInt(x.max_followers) },
        { key: 'days', label: 'Active days', align: 'right', render: (x) => fmtInt(x.active_days) },
        { key: 'span', label: 'Active', render: (x) => <span className="whitespace-nowrap text-xs">{fmtDay(x.first_post)} → {fmtDay(x.last_post)}</span> },
      ]} />
    </Card>
  )
}

function Mix({ g }) {
  const langs = g.languages.map((l) => ({ ...l, name: langName(l.language || 'unknown') }))
  const countries = g.countries.map((c) => ({ ...c, name: c.country || 'Unknown' }))
  const bar = (data, key, color) => (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, left: 8, bottom: 0 }}>
        <CartesianGrid {...gridProps} horizontal={false} vertical />
        <XAxis type="number" {...axisProps} tickFormatter={fmtCompact} />
        <YAxis type="category" dataKey={key} {...axisProps} width={110} />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
        <Bar dataKey="posts" name="Posts" fill={color} radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card title="Languages" subtitle="gold/daily_activity grouped by language">{bar(langs, 'name', 'var(--s3)')}</Card>
      <Card title="Countries" subtitle="Account-level region field">{bar(countries, 'name', 'var(--s2)')}</Card>
      <Card title="Day of week" subtitle="All posts, UTC">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={g.weekday} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="weekday" {...axisProps} />
            <YAxis {...axisProps} width={44} tickFormatter={fmtCompact} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
            <Bar dataKey="posts" name="Posts" fill="var(--s7)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}

const VIEWS = [{ id: 'activity', label: 'Activity over time' }, { id: 'hashtags', label: 'Hashtags' },
  { id: 'accounts', label: 'Accounts' }, { id: 'mix', label: 'Languages & countries' }]

export default function GoldTab({ r }) {
  const [view, setView] = useView(VIEWS)
  const g = r.spark_gold_summary
  if (!g) return <NotRun cmd="python -m bigdata.spark.pipeline" />
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'activity' && <Activity g={g} />}
      {view === 'hashtags' && <Hashtags g={g} />}
      {view === 'accounts' && <Accounts g={g} />}
      {view === 'mix' && <Mix g={g} />}
      <RunInfo r={g} />
    </>
  )
}
