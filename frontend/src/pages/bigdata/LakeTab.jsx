import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, Note, Table } from '../../components/ui'
import { ChartTooltip, Legend, axisProps, gridProps } from '../../charts/common'
import { fmtBytes, fmtCompact, fmtInt } from '../../utils/format'
import { NotRun, RunInfo, Stat, ViewSwitch, sec, useView } from './shared'

const LAYER_INFO = {
  bronze: { text: 'Raw rows exactly as received, all strings, plus source file and load time. Nothing is thrown away, so silver can always be rebuilt.' },
  silver: { text: 'Validated, cleaned and de-duplicated posts with real types (timestamps, ints, arrays of hashtags). Partitioned by year and month.' },
  gold: { text: 'Small aggregate tables built for questions the dashboard asks: activity per day, hashtags, accounts.' },
}

function Layers({ p, lake }) {
  if (!p) return <NotRun cmd="python -m bigdata.spark.pipeline" />
  const L = p.layers
  const chart = [
    { name: 'Raw CSV', bytes: L.raw_csv.bytes, fill: 'var(--s8)' },
    { name: 'Bronze', bytes: L.bronze.bytes, fill: 'var(--s2)' },
    { name: 'Silver', bytes: L.silver.bytes, fill: 'var(--s1)' },
    { name: 'Gold', bytes: L.gold.bytes, fill: 'var(--s3)' },
  ]
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      {[['bronze', L.bronze, 'var(--s2)'], ['silver', L.silver, 'var(--s1)'], ['gold', L.gold, 'var(--s3)']].map(([k, l, c]) => (
        <Card key={k} title={<span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: c }} />{k[0].toUpperCase() + k.slice(1)} layer</span>}
          subtitle={`data/lake/${k}`}>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Size" value={fmtBytes(l.bytes)} />
            <Stat label="Files" value={fmtInt(l.files)} />
            <Stat label={k === 'gold' ? 'Tables' : 'Rows'} value={k === 'gold' ? Object.keys(l.tables).length : fmtCompact(l.rows)} hint={k === 'gold' ? null : fmtInt(l.rows)} />
          </div>
          <p className="mt-3 text-xs text-ink-2">{LAYER_INFO[k].text}</p>
        </Card>
      ))}
      <Card className="xl:col-span-2" title="Storage per layer" subtitle="Same data, from CSV text to compressed columnar Parquet">
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={chart} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="name" {...axisProps} />
            <YAxis {...axisProps} width={60} tickFormatter={fmtBytes} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={fmtBytes} />} />
            <Bar dataKey="bytes" name="Size" radius={[4, 4, 0, 0]} isAnimationActive={false}
              label={{ position: 'top', fontSize: 11, fill: 'var(--ink-2)', formatter: fmtBytes }}>
              {chart.map((c) => <Cell key={c.name} fill={c.fill} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <Note>Silver is {(L.raw_csv.bytes / L.silver.bytes).toFixed(1)}× smaller than the raw CSV while holding more structure (typed columns, extracted hashtags and mentions).</Note>
      </Card>
      <Card title="What is on disk now" subtitle="Live listing from /api/bigdata/lake">
        <Async state={lake} height={160}>
          {(d) => (
            <Table dense rowKey={(t) => `${t.layer}.${t.table}`}
              rows={d.layers.flatMap((l) => l.tables.map((t) => ({ ...t, layer: l.layer })))}
              columns={[
                { key: 'table', label: 'Table', render: (t) => <code className="text-xs">{t.layer}/{t.table}</code> },
                { key: 'files', label: 'Files', align: 'right', render: (t) => fmtInt(t.files) },
                { key: 'bytes', label: 'Size', align: 'right', render: (t) => fmtBytes(t.bytes) },
              ]} />
          )}
        </Async>
      </Card>
      <div className="xl:col-span-3"><RunInfo r={p} /></div>
    </div>
  )
}

function Formats({ f }) {
  if (!f) return <NotRun cmd="python -m bigdata.spark.benchmarks formats" />
  const codecs = f.codecs.map((c) => ({ ...c, mb: c.bytes / 1e6 }))
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Compression codecs" subtitle="The silver table written with each codec">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={codecs} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="codec" {...axisProps} />
            <YAxis {...axisProps} width={60} tickFormatter={fmtBytes} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={fmtBytes} />} />
            <Bar dataKey="bytes" name="Size" fill="var(--s1)" radius={[4, 4, 0, 0]} isAnimationActive={false}
              label={{ position: 'top', fontSize: 11, fill: 'var(--ink-2)', formatter: fmtBytes }} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card title="Size and write time" subtitle="Smaller files cost more CPU to write">
        <Table dense rowKey={(c) => c.codec} rows={f.codecs} columns={[
          { key: 'codec', label: 'Format / codec' },
          { key: 'bytes', label: 'Size', align: 'right', render: (c) => fmtBytes(c.bytes) },
          { key: 'write', label: 'Write time', align: 'right', render: (c) => sec(c.write_sec) },
        ]} />
        <h3 className="mb-1 mt-4 text-xs font-semibold text-ink">Layers</h3>
        <Table dense rowKey={(c) => c.layer} rows={f.storage} columns={[
          { key: 'layer', label: 'Layer' }, { key: 'format', label: 'Format' },
          { key: 'files', label: 'Files', align: 'right', render: (c) => fmtInt(c.files) },
          { key: 'bytes', label: 'Size', align: 'right', render: (c) => fmtBytes(c.bytes) },
        ]} />
        <Note>Snappy is the default: nearly as small as gzip but much cheaper to read and write. zstd is the best ratio-for-speed alternative.</Note>
        <RunInfo r={f} />
      </Card>
    </div>
  )
}

function Queries({ f }) {
  if (!f) return <NotRun cmd="python -m bigdata.spark.benchmarks formats" />
  const rows = f.queries.map((q) => ({ ...q, name: q.description }))
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <Card title="Same question, three storage layouts" subtitle={`Median of ${f.params.repeat} runs, Spark SQL`}>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="query" {...axisProps} tickFormatter={(v) => v.replaceAll('_', ' ')} />
            <YAxis {...axisProps} width={40} tickFormatter={(v) => `${v}s`} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v) => sec(v)} labelFormatter={(v) => rows.find((r) => r.query === v)?.description} />} />
            <Bar dataKey="csv_sec" name="CSV" fill="var(--s8)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="parquet_sec" name="Parquet (bronze)" fill="var(--s2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="partitioned_sec" name="Partitioned Parquet (silver)" fill="var(--s1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <Legend items={[{ key: 'c', label: 'CSV', color: 'var(--s8)' }, { key: 'p', label: 'Parquet (bronze)', color: 'var(--s2)' },
          { key: 's', label: 'Partitioned Parquet (silver)', color: 'var(--s1)' }]} />
      </Card>
      <Card title="Why partitioned Parquet wins" subtitle="Files read and speed-up">
        <Table dense rowKey={(q) => q.query} rows={rows} columns={[
          { key: 'description', label: 'Query', render: (q) => <span className="text-xs">{q.description}</span> },
          { key: 'files', label: 'Silver files read', align: 'right', render: (q) => `${q.silver_files_read} / ${q.silver_files_total}` },
          { key: 'speedup', label: 'vs CSV', align: 'right', render: (q) => <b className="text-ink">{q.speedup_vs_csv}×</b> },
        ]} />
        <ul className="mt-3 space-y-1.5 text-xs text-ink-2">
          <li><b className="text-ink">Column pruning</b>: Parquet stores each column separately, so a query reads only the columns it uses. CSV must parse every field of every row.</li>
          <li><b className="text-ink">Partition pruning</b>: a filter on year/month skips whole folders before any file is opened.</li>
          <li><b className="text-ink">Pre-computed fields</b>: silver already holds parsed timestamps and hashtag arrays, so no regex runs at query time.</li>
        </ul>
        <RunInfo r={f} />
      </Card>
    </div>
  )
}

function Partitions({ p }) {
  if (!p) return <NotRun cmd="python -m bigdata.spark.pipeline" />
  const rows = p.silver_partitions.map((x) => ({ ...x, label: `${x.year}-${String(x.month).padStart(2, '0')}` }))
  const biggest = [...rows].sort((a, b) => b.bytes - a.bytes)[0]
  return (
    <Card title="Silver partitions" subtitle={`${rows.length} folders: data/lake/silver/posts/year=YYYY/month=M`}>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="label" {...axisProps} interval={5} />
          <YAxis {...axisProps} width={60} tickFormatter={fmtBytes} />
          <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={fmtBytes} />} />
          <Bar dataKey="bytes" name="Partition size" fill="var(--s7)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <Note>Partitions are uneven because activity was uneven: the largest is {biggest.label} ({fmtBytes(biggest.bytes)}). Partition skew like this is
        why a shard key or partition column has to be chosen from the data's real distribution.</Note>
    </Card>
  )
}

const VIEWS = [{ id: 'layers', label: 'Layers' }, { id: 'formats', label: 'Formats & codecs' },
  { id: 'queries', label: 'Query speed' }, { id: 'partitions', label: 'Partitions' }]

export default function LakeTab({ r, lake }) {
  const [view, setView] = useView(VIEWS)
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'layers' && <Layers p={r.spark_pipeline} lake={lake} />}
      {view === 'formats' && <Formats f={r.lake_formats} />}
      {view === 'queries' && <Queries f={r.lake_formats} />}
      {view === 'partitions' && <Partitions p={r.spark_pipeline} />}
    </>
  )
}
