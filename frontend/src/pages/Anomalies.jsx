import { useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, KpiCard, Note, PageHeader, Segmented, SourceBadge, Table } from '../components/ui'
import { ChartTooltip, axisProps, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtDay, fmtInt, fmtPct } from '../utils/format'

const REASON_LABELS = {
  volume_spike: 'Volume spike', volume_drop: 'Volume drop', negativity_surge: 'Negativity surge',
  negativity_drop: 'Negativity drop', iqr_outlier: 'IQR outlier', isolation_forest: 'Isolation Forest',
}
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const RAMP = ['var(--q1)', 'var(--q2)', 'var(--q3)', 'var(--q4)', 'var(--q5)', 'var(--q6)', 'var(--q7)']

function Heatmap({ cells }) {
  const max = Math.max(...cells.map((c) => c.posts), 1)
  const get = (d, h) => cells.find((c) => c.dow === d && c.hour === h)?.posts || 0
  return (
    <div className="overflow-x-auto">
      <div className="inline-grid min-w-full gap-[2px]" style={{ gridTemplateColumns: `2.5rem repeat(24, minmax(18px, 1fr))` }}>
        <div />
        {Array.from({ length: 24 }, (_, h) => <div key={h} className="text-center text-[10px] text-muted">{h % 3 === 0 ? h : ''}</div>)}
        {DOW.map((name, i) => (
          <div key={name} className="contents">
            <div className="pr-1 text-right text-[11px] leading-[22px] text-muted">{name}</div>
            {Array.from({ length: 24 }, (_, h) => {
              const v = get(i + 1, h)
              const step = Math.min(RAMP.length - 1, Math.floor((v / max) * RAMP.length))
              return <div key={h} title={`${name} ${h}:00 UTC: ${fmtInt(v)} posts`} className="h-[22px] rounded-[3px]" style={{ background: RAMP[step] }} />
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Anomalies() {
  const { filters } = useFilters()
  const [z, setZ] = useState(3)
  const an = useApi('/api/analytics/anomalies', { ...filters, z })
  const act = useApi('/api/analytics/activity', filters)

  return (
    <>
      <PageHeader title="Time patterns & anomalies"
        description="Days whose activity departs from the recent norm, found three ways: a rolling z-score computed inside MongoDB with $setWindowFields, the IQR rule, and an Isolation Forest on daily features.">
        <div className="flex items-center gap-2">
          <Segmented label="z threshold" value={z} onChange={setZ} options={[{ value: 2.5, label: 'z ≥ 2.5' }, { value: 3, label: 'z ≥ 3' }, { value: 4, label: 'z ≥ 4' }]} />
          <SourceBadge meta={an.data?.meta} />
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KpiCard label="Days analysed" loading={!an.data} value={fmtInt(an.data?.counts?.days)} />
        <KpiCard label="Anomalous days" loading={!an.data} value={fmtInt(an.data?.counts?.anomalous_days)} />
        <KpiCard label="Volume z-score" loading={!an.data} value={fmtInt(an.data?.counts?.volume_z)} />
        <KpiCard label="Negativity z-score" loading={!an.data} value={fmtInt(an.data?.counts?.negativity_z)} />
        <KpiCard label="Isolation Forest" loading={!an.data} value={fmtInt(an.data?.counts?.isolation_forest)} />
      </div>

      <Card className="mt-4" title="Daily posts vs expected" subtitle="Line: daily posts. Dashed: rolling 28-day mean of previous days. Dots: days flagged by the z-score rule.">
        <Async state={an} height={320} isEmpty={(x) => !x.series.length}>
          {(x) => {
            const flagged = x.series.filter((d) => d.reasons.some((r) => r.startsWith('volume')))
            return (
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={x.series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="day" type="category" allowDuplicatedCategory={false} tickFormatter={(v) => fmtDay(v)} {...axisProps} minTickGap={60} />
                  <YAxis tickFormatter={fmtCompact} {...axisProps} width={44} />
                  <Tooltip content={<ChartTooltip labelFormatter={fmtDay} valueFormatter={(v) => fmtInt(v)} />} />
                  <Line dataKey="posts" name="Posts" stroke="var(--s1)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Line dataKey="expected" name="Expected (28-day mean)" stroke="var(--ink-muted)" strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
                  <Scatter data={flagged} dataKey="posts" name="Flagged" fill="var(--neg)" shape="circle" isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )
          }}
        </Async>
      </Card>

      <div className="mt-4 grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3" title="Flagged days" subtitle="Sorted by number of methods that agree, then by |z|">
          <Async state={an} height={360} isEmpty={(x) => !x.anomalies.length}>
            {(x) => (
              <div className="max-h-[440px] overflow-y-auto">
                <Table dense rowKey={(r) => r.day} rows={x.anomalies} columns={[
                  { key: 'day', label: 'Day', render: (r) => <span className="whitespace-nowrap text-ink">{fmtDay(r.day)}</span> },
                  { key: 'posts', label: 'Posts', align: 'right', render: (r) => fmtInt(r.posts) },
                  { key: 'expected', label: 'Expected', align: 'right', render: (r) => fmtInt(r.expected) },
                  { key: 'vol_z', label: 'Volume z', align: 'right', render: (r) => r.vol_z ?? '–' },
                  { key: 'neg', label: 'Negative', align: 'right', render: (r) => (r.neg_share === null ? '–' : fmtPct(100 * r.neg_share)) },
                  { key: 'reasons', label: 'Detected by', render: (r) => (
                    <div className="flex flex-wrap gap-1">{r.reasons.map((x) => <span key={x} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">{REASON_LABELS[x]}</span>)}</div>) },
                ]} />
              </div>
            )}
          </Async>
        </Card>
        <Card className="xl:col-span-2" title="When accounts posted" subtitle="Posts by weekday and hour (UTC); darker = more">
          <Async state={act} height={240} isEmpty={(x) => !x.cells.length}>
            {(x) => <Heatmap cells={x.cells} />}
          </Async>
          <div className="mt-3 space-y-1">
            <Note>Computed live with $isoDayOfWeek and $hour on created_at.</Note>
            {an.data?.methods && <Note>Isolation Forest: {an.data.methods.isolation_forest}.</Note>}
          </div>
        </Card>
      </div>
    </>
  )
}
