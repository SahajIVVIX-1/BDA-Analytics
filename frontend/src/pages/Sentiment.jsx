import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, Note, PageHeader, Segmented, SourceBadge, Table } from '../components/ui'
import { ChartTooltip, Legend, SENTIMENT_COLORS, SENTIMENTS, SentimentBar, axisProps, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { useFilters } from '../hooks/useFilters'
import { fmtCompact, fmtDay, fmtInt, fmtPct, fmtSigned, langName, tickForGranularity } from '../utils/format'

function ModelCard() {
  const perf = useApi('/api/performance')
  const ev = perf.data?.results?.sentiment_evaluation
  if (!ev) return null
  const rows = Object.entries(ev.results).map(([k, v]) => ({ model: k, ...v }))
  const names = { vader: 'VADER (lexicon)', tfidf_nb: 'TF-IDF + Naive Bayes', tfidf_logreg: 'TF-IDF + Logistic Regression' }
  return (
    <Card title="Model evaluation" subtitle={`${ev.dataset}; test set n = ${fmtInt(ev.sizes.test)}. Selected: ${names[ev.best_model]}`}>
      <Table dense rowKey={(r) => r.model} rows={rows} columns={[
        { key: 'model', label: 'Model', render: (r) => <span className={r.model === ev.best_model ? 'font-medium text-ink' : ''}>{names[r.model]}</span> },
        { key: 'accuracy', label: 'Accuracy', align: 'right', render: (r) => r.accuracy.toFixed(3) },
        { key: 'macro_f1', label: 'Macro F1', align: 'right', render: (r) => r.macro_f1.toFixed(3) },
        { key: 'macro_recall', label: 'Macro recall', align: 'right', render: (r) => r.macro_recall.toFixed(3) },
        { key: 'tps', label: 'Texts / s', align: 'right', render: (r) => fmtInt(r.texts_per_second) },
      ]} />
      <div className="mt-2"><Note>Measured on TweetEval (human-labelled tweets), not on this dataset; labels for the troll tweets themselves are model predictions.</Note></div>
    </Card>
  )
}

export default function Sentiment() {
  const { filters } = useFilters()
  const [granularity, setGranularity] = useState('week')
  const st = useApi('/api/analytics/sentiment', { ...filters, granularity })

  return (
    <>
      <PageHeader title="Sentiment" description="Three-class sentiment (positive / neutral / negative) predicted for every English post with the TF-IDF + Logistic Regression model.">
        <SourceBadge meta={st.data?.meta} />
      </PageHeader>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Distribution" subtitle={st.data && `${fmtInt(st.data.distribution.analysed)} posts analysed`}>
          <Async state={st} height={260} isEmpty={(x) => !x.distribution.analysed}>
            {(x) => {
              const rows = SENTIMENTS.map((k) => ({ k, n: x.distribution.counts[k], pct: x.distribution.percent[k] }))
              return (
                <>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid {...gridProps} />
                      <XAxis dataKey="k" {...axisProps} tickFormatter={(v) => v[0].toUpperCase() + v.slice(1)} />
                      <YAxis tickFormatter={fmtCompact} {...axisProps} width={44} />
                      <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v, p) => `${fmtInt(v)} (${fmtPct(p.payload.pct)})`} />} />
                      <Bar dataKey="n" name="Posts" radius={[4, 4, 0, 0]} barSize={48} isAnimationActive={false}
                        label={{ position: 'top', fontSize: 11, fill: 'var(--ink-2)', formatter: (v) => fmtCompact(v) }}>
                        {rows.map((r) => <Cell key={r.k} fill={SENTIMENT_COLORS[r.k]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="mt-2 text-xs text-muted">Average score (P(pos) − P(neg)): <span className="font-medium text-ink">{fmtSigned(x.avg_score, 3)}</span></p>
                </>
              )
            }}
          </Async>
        </Card>
        <Card className="xl:col-span-2" title="Sentiment over time" subtitle="Share of analysed posts per period; periods with under 100 analysed posts are left blank"
          actions={<Segmented label="Granularity" value={granularity} onChange={setGranularity} options={['day', 'week', 'month']} />}>
          <Async state={st} height={260} isEmpty={(x) => !x.over_time.length}>
            {(x) => (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={x.over_time} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="t" tickFormatter={tickForGranularity(granularity)} {...axisProps} minTickGap={40} />
                    <YAxis tickFormatter={(v) => `${v}%`} {...axisProps} width={40} domain={[0, 'auto']} />
                    <Tooltip content={<ChartTooltip labelFormatter={fmtDay} valueFormatter={(v) => fmtPct(v)} />} />
                    <Line dataKey="positive_pct" name="Positive" stroke="var(--pos)" strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Line dataKey="negative_pct" name="Negative" stroke="var(--neg)" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
                <Legend items={[{ key: 'p', label: 'Positive %', color: 'var(--pos)' }, { key: 'n', label: 'Negative %', color: 'var(--neg)' }]} />
              </>
            )}
          </Async>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Sentiment by topic" subtitle="English topics, sorted by volume; bar = positive / neutral / negative mix">
          <Async state={st} height={360} isEmpty={(x) => !x.by_topic.length}>
            {(x) => (
              <ul className="space-y-2">
                {x.by_topic.filter((t) => t.key.startsWith('en-')).slice(0, 16).map((t) => (
                  <li key={t.key} className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm">
                    <span className="truncate text-ink" title={t.label}>{t.label}</span>
                    <SentimentBar positive={t.positive} neutral={t.neutral} negative={t.negative} height={10} />
                    <span className={`text-right text-xs tabular font-medium ${t.net_sentiment >= 0 ? 'text-pos' : 'text-neg'}`}>{fmtSigned(100 * t.net_sentiment, 0)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Async>
          <div className="mt-3"><Legend items={SENTIMENTS.map((k) => ({ key: k, label: k, color: SENTIMENT_COLORS[k] }))} /></div>
          <div className="mt-1"><Note>Right column: net sentiment = (positive − negative) / analysed × 100.</Note></div>
        </Card>
        <Card title="Net sentiment by country" subtitle="Countries with ≥ 100 analysed posts (account-level region)">
          <Async state={st} height={360} isEmpty={(x) => !x.by_country.length}>
            {(x) => (
              <ResponsiveContainer width="100%" height={Math.max(200, x.by_country.slice(0, 15).length * 24)}>
                <BarChart data={x.by_country.slice(0, 15).map((r) => ({ ...r, net: +(100 * r.net_sentiment).toFixed(1) }))} layout="vertical" margin={{ left: 8, right: 24 }}>
                  <CartesianGrid {...gridProps} horizontal={false} vertical />
                  <XAxis type="number" {...axisProps} domain={['auto', 'auto']} />
                  <YAxis type="category" dataKey="key" {...axisProps} width={120} />
                  <ReferenceLine x={0} stroke="var(--axis)" />
                  <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v, p) => `${fmtSigned(v)} (n=${fmtInt(p.payload.analysed)})`} />} />
                  <Bar dataKey="net" name="Net sentiment" barSize={12} radius={4} isAnimationActive={false}>
                    {x.by_country.slice(0, 15).map((r) => <Cell key={r.key} fill={r.net_sentiment >= 0 ? 'var(--pos)' : 'var(--neg)'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Async>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Sentiment by language" subtitle={st.data?.note}>
          <Async state={st} height={160}>
            {(x) => (
              <Table dense rowKey={(r) => r.key} rows={x.by_language} columns={[
                { key: 'key', label: 'Language', render: (r) => langName(r.key) },
                { key: 'analysed', label: 'Analysed', align: 'right', render: (r) => fmtInt(r.analysed) },
                { key: 'positive_pct', label: 'Positive', align: 'right', render: (r) => fmtPct(r.positive_pct) },
                { key: 'neutral_pct', label: 'Neutral', align: 'right', render: (r) => fmtPct(r.neutral_pct) },
                { key: 'negative_pct', label: 'Negative', align: 'right', render: (r) => fmtPct(r.negative_pct) },
              ]} />
            )}
          </Async>
        </Card>
        <ModelCard />
      </div>
    </>
  )
}
