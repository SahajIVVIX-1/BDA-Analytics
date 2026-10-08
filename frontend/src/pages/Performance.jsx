import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, EmptyState, Note, PageHeader, Segmented, Table } from '../components/ui'
import { ChartTooltip, Legend, axisProps, colorMap, gridProps } from '../charts/common'
import { useApi } from '../hooks/useApi'
import { fmtBytes, fmtCompact, fmtDateTime, fmtInt, fmtMs } from '../utils/format'

function Hardware({ hw, runAt }) {
  if (!hw) return null
  return (
    <p className="text-xs text-muted">
      Ran {fmtDateTime(runAt)} on {hw.label}: {hw.processor || hw.machine}, {hw.cpu_count} CPUs{hw.ram_gb ? `, ${hw.ram_gb} GB RAM` : ''},
      MongoDB {hw.mongodb}{hw.wiredtiger_cache_gb ? ` (WiredTiger cache ${hw.wiredtiger_cache_gb} GB)` : ''}, Python {hw.python}.
    </p>
  )
}

function Missing({ name }) {
  return <EmptyState title="Not measured yet" hint={`Run: python experiments/run_experiments.py ${name}`} />
}

function IngestionScaling({ r }) {
  if (!r) return <Missing name="ingestion" />
  const rows = r.results.map((x) => ({ ...x, label: fmtCompact(x.inserted) }))
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} />
            <YAxis {...axisProps} width={44} tickFormatter={(v) => `${v}s`} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v) => `${v.toFixed(1)} s`} />} />
            <Bar dataKey="elapsed_sec" name="Load" stackId="a" fill="var(--s1)" isAnimationActive={false} />
            <Bar dataKey="index_build_sec" name="Index build" stackId="a" fill="var(--s2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <Table dense rowKey={(x) => x.label} rows={rows} columns={[
          { key: 'label', label: 'Records', render: (x) => fmtInt(x.inserted) },
          { key: 'elapsed_sec', label: 'Load', align: 'right', render: (x) => `${x.elapsed_sec.toFixed(1)} s` },
          { key: 'records_per_sec', label: 'Records/s', align: 'right', render: (x) => fmtInt(x.records_per_sec) },
          { key: 'index_build_sec', label: 'Indexes', align: 'right', render: (x) => `${x.index_build_sec.toFixed(1)} s` },
          { key: 'storage_mb', label: 'Storage', align: 'right', render: (x) => `${fmtInt(x.storage_mb)} MB` },
          { key: 'index_mb', label: 'Index size', align: 'right', render: (x) => `${fmtInt(x.index_mb)} MB` },
        ]} />
      </div>
      <Legend items={[{ key: 'l', label: 'Load (read + clean + bulk insert)', color: 'var(--s1)' }, { key: 'i', label: 'Secondary index build', color: 'var(--s2)' }]} />
    </>
  )
}

function SimpleBar({ r, x, y, xLabel, yFmt = fmtInt, name }) {
  if (!r) return <Missing name={name} />
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={r.results} margin={{ top: 16, right: 8, left: 0, bottom: 12 }}>
        <CartesianGrid {...gridProps} />
        <XAxis dataKey={x} {...axisProps} tickFormatter={(v) => `${v}`} label={{ value: xLabel, position: 'insideBottom', offset: -2, fontSize: 11, fill: 'var(--ink-muted)' }} height={36} />
        <YAxis {...axisProps} width={48} tickFormatter={fmtCompact} />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={yFmt} />} />
        <Bar dataKey={y} name="Records / s" fill="var(--s1)" radius={[4, 4, 0, 0]} barSize={36} isAnimationActive={false}
          label={{ position: 'top', fontSize: 11, fill: 'var(--ink-2)', formatter: fmtCompact }} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function IndexExperiment({ r }) {
  const sizes = [...new Set(r?.results.map((x) => x.size) || [])]
  const [size, setSize] = useState(null)
  if (!r) return <Missing name="queries" />
  const s = size || sizes[sizes.length - 1]
  const rows = r.results.filter((x) => x.size === s)
  const queries = [...new Set(r.results.map((x) => x.query))]
  const colors = colorMap(queries)
  const scaling = sizes.map((sz) => {
    const p = { size: sz }
    r.results.filter((x) => x.size === sz).forEach((x) => { p[`${x.query}`] = x.collscan_ms; p[`${x.query}__idx`] = x.indexed_ms })
    return p
  })
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Collection size</span>
        <Segmented label="Collection size" value={s} onChange={setSize} options={sizes} />
      </div>
      <Table dense rowKey={(x) => x.query} rows={rows} columns={[
        { key: 'query', label: 'Query', render: (x) => <span className="text-ink">{x.query.replaceAll('_', ' ')}</span> },
        { key: 'index', label: 'Index used', render: (x) => <code className="text-xs">{x.index}</code> },
        { key: 'n', label: 'Returned', align: 'right', render: (x) => fmtInt(x.indexed_n_returned) },
        { key: 'scan_ms', label: 'Scan time', align: 'right', render: (x) => fmtMs(x.collscan_ms) },
        { key: 'scan_docs', label: 'Docs examined (scan)', align: 'right', render: (x) => fmtInt(x.collscan_docs_examined) },
        { key: 'idx_ms', label: 'Indexed time', align: 'right', render: (x) => fmtMs(x.indexed_ms) },
        { key: 'idx_docs', label: 'Docs examined (index)', align: 'right', render: (x) => fmtInt(x.indexed_docs_examined) },
        { key: 'idx_keys', label: 'Keys examined', align: 'right', render: (x) => fmtInt(x.indexed_keys_examined) },
        { key: 'speedup', label: 'Speed-up', align: 'right', render: (x) => (x.indexed_ms < 1 ? <span className="text-muted" title="index time below the 1 ms timer resolution">index &lt;1 ms</span> : <span className="font-medium text-ink">{x.speedup}×</span>) },
      ]} />
      {sizes.length > 1 && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium text-ink-2">Collection scan time grows with size</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={scaling} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="size" {...axisProps} />
                <YAxis {...axisProps} width={48} tickFormatter={(v) => `${v} ms`} />
                <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v} ms`} nameFormatter={(n) => n.replaceAll('_', ' ')} />} />
                {queries.map((q) => <Line key={q} dataKey={q} name={q} stroke={colors[q]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-ink-2">Indexed time stays small</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={scaling} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="size" {...axisProps} />
                <YAxis {...axisProps} width={48} tickFormatter={(v) => `${v} ms`} />
                <Tooltip content={<ChartTooltip valueFormatter={(v) => `${v} ms`} nameFormatter={(n) => n.replace('__idx', '').replaceAll('_', ' ')} />} />
                {queries.map((q) => <Line key={q} dataKey={`${q}__idx`} name={`${q}__idx`} stroke={colors[q]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      <div className="mt-2"><Legend items={queries.map((q) => ({ key: q, label: q.replaceAll('_', ' '), color: colors[q] }))} /></div>
    </>
  )
}

function Aggregations({ r }) {
  if (!r) return <Missing name="aggregations" />
  const sizes = [...new Set(r.results.pipelines.map((x) => x.size))]
  const names = [...new Set(r.results.pipelines.map((x) => x.pipeline))]
  const colors = colorMap(names)
  const data = sizes.map((s) => {
    const p = { size: s }
    r.results.pipelines.filter((x) => x.size === s).forEach((x) => { p[x.pipeline] = x.ms })
    return p
  })
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-medium text-ink-2">Pipeline time by collection size (median of {r.params.runs} runs)</p>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="size" {...axisProps} />
            <YAxis {...axisProps} width={56} tickFormatter={(v) => fmtMs(v)} />
            <Tooltip content={<ChartTooltip valueFormatter={fmtMs} nameFormatter={(n) => n.replaceAll('_', ' ')} />} />
            {names.map((n) => <Line key={n} dataKey={n} name={n} stroke={colors[n]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
          </LineChart>
        </ResponsiveContainer>
        <Legend items={names.map((n) => ({ key: n, label: n.replaceAll('_', ' '), color: colors[n] }))} />
      </div>
      <div>
        <p className="mb-1 text-xs font-medium text-ink-2">Pre-aggregated cube vs live aggregation on posts (full collection)</p>
        <Table dense rowKey={(x) => x.query} rows={r.results.cube_vs_live} columns={[
          { key: 'query', label: 'Dashboard query', render: (x) => <span className="text-ink">{x.query.replaceAll('_', ' ')}</span> },
          { key: 'live_ms', label: 'Live (posts)', align: 'right', render: (x) => fmtMs(x.live_ms) },
          { key: 'cube_ms', label: 'Cube', align: 'right', render: (x) => fmtMs(x.cube_ms) },
          { key: 'speedup', label: 'Speed-up', align: 'right', render: (x) => <span className="font-medium text-ink">{x.speedup}×</span> },
        ]} />
        <div className="mt-3 text-xs text-muted">
          Rollup build (all $merge pipelines): <span className="text-ink">{r.results.rollup_build.total_sec} s</span>. Sizes:{' '}
          {Object.entries(r.results.collection_sizes).map(([k, v]) => `${k} ${fmtCompact(v)}`).join(' · ')}
        </div>
      </div>
    </div>
  )
}

function Nlp({ r, ev }) {
  if (!r) return <Missing name="nlp" />
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-medium text-ink-2">Model throughput ({fmtInt(r.params.sample)} English posts, single process)</p>
        <Table dense rowKey={(x) => x.task} rows={r.results.models} columns={[
          { key: 'task', label: 'Task', render: (x) => x.task.replaceAll('_', ' ') },
          { key: 'ms', label: 'Time', align: 'right', render: (x) => fmtMs(x.ms) },
          { key: 'tps', label: 'Texts / s', align: 'right', render: (x) => fmtInt(x.texts_per_sec) },
        ]} />
      </div>
      <div>
        <p className="mb-1 text-xs font-medium text-ink-2">End-to-end enrichment of {fmtInt(r.params.e2e_posts)} posts (read, models, bulk write)</p>
        <Table dense rowKey={(x) => x.workers} rows={r.results.end_to_end} columns={[
          { key: 'workers', label: 'Processes', align: 'right' },
          { key: 'elapsed_sec', label: 'Total', align: 'right', render: (x) => `${x.elapsed_sec} s` },
          { key: 'db', label: 'of which DB writes', align: 'right', render: (x) => `${x.db_write_sec} s` },
          { key: 'pps', label: 'Posts / s', align: 'right', render: (x) => fmtInt(x.posts_per_sec) },
        ]} />
        {ev && <div className="mt-2"><Note>Accuracy on TweetEval is on the Sentiment page (best: {ev.best_model}, macro F1 {ev.results[ev.best_model].macro_f1}).</Note></div>}
      </div>
    </div>
  )
}

function Explain() {
  const [q, setQ] = useState('sentiment_range')
  const ex = useApi(`/api/performance/explain/${q}`)
  return (
    <>
      <Segmented label="Query" value={q} onChange={setQ} options={['sentiment_range', 'hashtag_lookup', 'language_range', 'user_timeline', 'text_search'].map((v) => ({ value: v, label: v.replace('_', ' ') }))} />
      <div className="mt-3">
        <Async state={ex} height={120}>
          {(x) => (
            <div className="grid gap-3 text-sm md:grid-cols-[1fr_auto]">
              <div>
                <p className="text-ink">{x.description}</p>
                <p className="mt-2 text-xs text-muted">Winning plan</p>
                <p className="font-mono text-xs text-ink-2">{x.winning_plan.join(' ← ')}</p>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                <dt className="text-muted">Returned</dt><dd className="text-right tabular text-ink">{fmtInt(x.n_returned)}</dd>
                <dt className="text-muted">Keys examined</dt><dd className="text-right tabular text-ink">{fmtInt(x.total_keys_examined)}</dd>
                <dt className="text-muted">Docs examined</dt><dd className="text-right tabular text-ink">{fmtInt(x.total_docs_examined)}</dd>
                <dt className="text-muted">Execution</dt><dd className="text-right tabular text-ink">{fmtMs(x.execution_ms)}</dd>
              </dl>
            </div>
          )}
        </Async>
      </div>
    </>
  )
}

export default function Performance() {
  const perf = useApi('/api/performance')
  const idx = useApi('/api/performance/indexes')
  const colls = useApi('/api/performance/collections')
  const res = perf.data?.results || {}

  return (
    <>
      <PageHeader title="Performance experiments" description="Measured results from experiments/run_experiments.py. Nothing on this page is estimated; experiments that have not run yet are marked.">
      </PageHeader>
      <Async state={perf} height={200}>
        {() => (
          <div className="space-y-4">
            <Card title="1 · Ingestion scaling" subtitle="CSV → clean → bulk insert into MongoDB at increasing dataset sizes"><IngestionScaling r={res.ingestion_scaling} /><Hardware hw={res.ingestion_scaling?.hardware} runAt={res.ingestion_scaling?.run_at} /></Card>
            <div className="grid gap-4 xl:grid-cols-3">
              <Card title="2 · Batch size" subtitle={res.ingestion_batch_size && `${fmtInt(res.ingestion_batch_size.params.records)} records`}>
                <SimpleBar r={res.ingestion_batch_size} x="batch_size" y="records_per_sec" xLabel="documents per insert_many" name="batch" />
                <Hardware hw={res.ingestion_batch_size?.hardware} runAt={res.ingestion_batch_size?.run_at} />
              </Card>
              <Card title="3 · Parallel cleaning" subtitle={res.ingestion_workers && `${fmtInt(res.ingestion_workers.params.records)} records`}>
                <SimpleBar r={res.ingestion_workers} x="workers" y="records_per_sec" xLabel="cleaning processes" name="workers" />
                <Hardware hw={res.ingestion_workers?.hardware} runAt={res.ingestion_workers?.run_at} />
              </Card>
              <Card title="4 · When to build indexes" subtitle={res.ingestion_index_mode && `${fmtInt(res.ingestion_index_mode.params.records)} records`}>
                {res.ingestion_index_mode ? (
                  <Table dense rowKey={(x) => x.index_mode} rows={res.ingestion_index_mode.results} columns={[
                    { key: 'index_mode', label: 'Strategy', render: (x) => (x.index_mode === 'upfront' ? 'All indexes during load' : 'Load, then build') },
                    { key: 'elapsed_sec', label: 'Load', align: 'right', render: (x) => <span className="whitespace-nowrap">{x.elapsed_sec.toFixed(1)} s</span> },
                    { key: 'index_build_sec', label: 'Build', align: 'right', render: (x) => <span className="whitespace-nowrap">{x.index_build_sec.toFixed(1)} s</span> },
                    { key: 'total', label: 'Total', align: 'right', render: (x) => <span className="whitespace-nowrap font-medium text-ink">{x.total_sec_including_indexes.toFixed(1)} s</span> },
                  ]} />
                ) : <Missing name="indexmode" />}
                <div className="mt-3"><Hardware hw={res.ingestion_index_mode?.hardware} runAt={res.ingestion_index_mode?.run_at} /></div>
              </Card>
            </div>
            <Card title="5 · Indexed query vs collection scan" subtitle="explain('executionStats'); collection scan forced with hint {$natural: 1}"><IndexExperiment r={res.index_vs_collscan} /><Hardware hw={res.index_vs_collscan?.hardware} runAt={res.index_vs_collscan?.run_at} /></Card>
            <Card title="6 · Aggregation pipelines" subtitle="$match / $group / $unwind / $lookup / $dateTrunc at increasing sizes"><Aggregations r={res.aggregation_scaling} /><Hardware hw={res.aggregation_scaling?.hardware} runAt={res.aggregation_scaling?.run_at} /></Card>
            <Card title="7 · NLP processing" subtitle="Sentiment and topic model throughput"><Nlp r={res.nlp_throughput} ev={res.sentiment_evaluation} /><Hardware hw={res.nlp_throughput?.hardware} runAt={res.nlp_throughput?.run_at} /></Card>
          </div>
        )}
      </Async>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Live explain()" subtitle="Run a representative query against the database now"><Explain /></Card>
        <Card title="Collections" subtitle="Live collStats">
          <Async state={colls} height={200}>
            {(x) => (
              <Table dense rowKey={(c) => c.collection} rows={x.collections} columns={[
                { key: 'collection', label: 'Collection', render: (c) => <code className="text-xs text-ink">{c.collection}</code> },
                { key: 'documents', label: 'Documents', align: 'right', render: (c) => fmtInt(c.documents) },
                { key: 'avg', label: 'Avg doc', align: 'right', render: (c) => fmtBytes(c.avg_doc_bytes) },
                { key: 'storage', label: 'On disk', align: 'right', render: (c) => fmtBytes(c.storage_bytes) },
                { key: 'idx', label: 'Indexes', align: 'right', render: (c) => `${c.indexes} · ${fmtBytes(c.index_bytes)}` },
              ]} />
            )}
          </Async>
        </Card>
      </div>

      <Card className="mt-4" title="Index design" subtitle="Every index, why it exists, and its current size">
        <Async state={idx} height={200}>
          {(x) => (
            <Table dense rowKey={(i) => `${i.collection}.${i.name}`} rows={x.indexes} columns={[
              { key: 'collection', label: 'Collection', render: (i) => <code className="text-xs">{i.collection}</code> },
              { key: 'keys', label: 'Keys', render: (i) => <code className="text-xs text-ink">{i.keys.map(([k, v]) => `${k}:${v}`).join(', ')}</code> },
              { key: 'reason', label: 'Why', render: (i) => <span className="text-xs">{i.reason}</span> },
              { key: 'size', label: 'Size', align: 'right', render: (i) => fmtBytes(i.size_bytes) },
            ]} />
          )}
        </Async>
      </Card>
    </>
  )
}
