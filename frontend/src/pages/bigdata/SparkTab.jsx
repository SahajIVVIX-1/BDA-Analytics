import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, Note, Table } from '../../components/ui'
import { ChartTooltip, Legend, axisProps, gridProps } from '../../charts/common'
import { fmtCompact, fmtInt } from '../../utils/format'
import { Code, NotRun, RunInfo, Stat, ViewSwitch, sec, useView } from './shared'

function Run({ p }) {
  if (!p) return <NotRun cmd="python -m bigdata.spark.pipeline" />
  const t = p.timings
  const stages = [
    { stage: 'Bronze (CSV → Parquet)', sec: t.bronze_sec },
    { stage: 'Validate', sec: t.validate_sec },
    { stage: 'Silver (clean + dedupe)', sec: t.silver_sec },
    { stage: 'Gold (aggregates)', sec: t.gold_sec },
  ]
  const funnel = [
    { step: 'Rows read', n: p.rows.raw },
    { step: 'Valid', n: p.rows.valid },
    { step: 'After de-duplication', n: p.rows.silver },
  ]
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Pipeline run" subtitle="python -m bigdata.spark.pipeline (raw CSV → bronze → silver → gold)">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Rows in" value={fmtCompact(p.rows.raw)} hint={`${p.layers.raw_csv.files} CSV files`} />
          <Stat label="Rows out" value={fmtCompact(p.rows.silver)} hint="silver posts" />
          <Stat label="Total time" value={sec(t.total_sec)} hint="all four stages" />
          <Stat label="Throughput" value={fmtCompact(p.throughput_rows_per_sec)} hint="rows / second" />
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={stages} layout="vertical" margin={{ top: 16, right: 40, left: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} horizontal={false} vertical />
            <XAxis type="number" {...axisProps} tickFormatter={(v) => `${v}s`} />
            <YAxis type="category" dataKey="stage" {...axisProps} width={160} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v) => sec(v)} />} />
            <Bar dataKey="sec" name="Time" fill="var(--s1)" radius={[0, 4, 4, 0]} barSize={20} isAnimationActive={false}
              label={{ position: 'right', fontSize: 11, fill: 'var(--ink-2)', formatter: (v) => sec(v) }} />
          </BarChart>
        </ResponsiveContainer>
        <RunInfo r={p} />
      </Card>
      <Card title="Rows through the pipeline" subtitle="Validation and de-duplication">
        <Table dense rowKey={(x) => x.step} rows={funnel} columns={[
          { key: 'step', label: 'Step' },
          { key: 'n', label: 'Rows', align: 'right', render: (x) => fmtInt(x.n) },
          { key: 'pct', label: 'Of input', align: 'right', render: (x) => `${((100 * x.n) / p.rows.raw).toFixed(3)}%` },
        ]} />
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Stat label="Rejected rows" value={fmtInt(Object.values(p.rows.invalid).reduce((a, b) => a + b, 0))}
            hint={Object.entries(p.rows.invalid).map(([k, v]) => `${k}: ${v}`).join(', ') || 'none'} />
          <Stat label="Duplicate tweet ids" value={fmtInt(p.rows.duplicates_removed)} hint="dropDuplicates(post_id)" />
        </div>
        <h3 className="mb-1 mt-4 text-xs font-semibold text-ink">Spark configuration</h3>
        <Table dense rowKey={(x) => x.k} rows={[
          { k: 'Master', v: p.params.master },
          { k: 'Default parallelism (tasks at once)', v: p.params.default_parallelism },
          { k: 'Shuffle partitions', v: p.params.shuffle_partitions },
          { k: 'Silver partitions (year/month folders)', v: p.layers.silver.partitions },
        ]} columns={[{ key: 'k', label: 'Setting' }, { key: 'v', label: 'Value', align: 'right' }]} />
      </Card>
    </div>
  )
}

function Scaling({ s }) {
  if (!s) return <NotRun cmd="python -m bigdata.spark.benchmarks scaling" />
  const maxCores = Math.max(...s.runs.map((x) => x.cores))
  const bySize = s.runs.filter((x) => x.cores === maxCores).map((x) => ({ ...x, label: fmtCompact(x.rows) }))
  const ideal = s.speedup.map((x) => ({ ...x, ideal: x.cores / s.speedup[0].cores }))
  const py = s.python_pipeline_reference || []
  const compare = bySize.map((x, i) => ({ label: x.label, spark: x.rows_per_sec, python: py[i]?.rows_per_sec }))
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card title="Data scaling" subtitle={`More rows, same ${maxCores} cores: silver + gold time`}>
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={bySize} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} />
            <YAxis {...axisProps} width={40} tickFormatter={(v) => `${v}s`} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={(v) => sec(v)} />} />
            <Bar dataKey="silver_sec" name="Silver" stackId="a" fill="var(--s1)" isAnimationActive={false} />
            <Bar dataKey="gold_sec" name="Gold" stackId="a" fill="var(--s3)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <Legend items={[{ key: 's', label: 'Silver', color: 'var(--s1)' }, { key: 'g', label: 'Gold', color: 'var(--s3)' }]} />
        <Note>Throughput rises with size because Spark's fixed start-up and scheduling cost is spread over more rows.</Note>
      </Card>
      <Card title="Core scaling (speed-up)" subtitle="Same full dataset, 1 → more cores">
        <ResponsiveContainer width="100%" height={230}>
          <LineChart data={ideal} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="cores" {...axisProps} tickFormatter={(v) => `${v} core${v > 1 ? 's' : ''}`} />
            <YAxis {...axisProps} width={36} tickFormatter={(v) => `${v}×`} />
            <Tooltip content={<ChartTooltip labelFormatter={(v) => `${v} cores`} valueFormatter={(v) => `${Number(v).toFixed(2)}×`} />} />
            <Line dataKey="ideal" name="Ideal (linear)" stroke="var(--axis)" strokeDasharray="4 4" dot={false} isAnimationActive={false} />
            <Line dataKey="speedup" name="Measured" stroke="var(--s2)" strokeWidth={2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <Table dense rowKey={(x) => x.cores} rows={s.speedup} columns={[
          { key: 'cores', label: 'Cores' },
          { key: 'total_sec', label: 'Time', align: 'right', render: (x) => sec(x.total_sec) },
          { key: 'speedup', label: 'Speed-up', align: 'right', render: (x) => `${x.speedup}×` },
          { key: 'efficiency', label: 'Efficiency', align: 'right', render: (x) => `${Math.round(x.efficiency * 100)}%` },
        ]} />
      </Card>
      <Card title="Spark vs the Python pipeline" subtitle="Rows per second at each dataset size">
        <ResponsiveContainer width="100%" height={230}>
          <BarChart data={compare} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} />
            <YAxis {...axisProps} width={44} tickFormatter={fmtCompact} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
            <Bar dataKey="spark" name="Spark (Parquet)" fill="var(--s2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="python" name="Python → MongoDB" fill="var(--s1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <Legend items={[{ key: 's', label: 'Spark (Parquet)', color: 'var(--s2)' }, { key: 'p', label: 'Python → MongoDB', color: 'var(--s1)' }]} />
        <Note>{s.note}</Note>
      </Card>
      <div className="xl:col-span-3"><RunInfo r={s} /></div>
    </div>
  )
}

function Plan({ p }) {
  if (!p) return <NotRun cmd="python -m bigdata.spark.pipeline" />
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <Card title="Physical plan of a one-month query" subtitle="silver.where('year = 2016 AND month = 10').groupBy('account_category').count()">
        <Code>{p.plans.partition_pruning}</Code>
      </Card>
      <Card title="How to read it" subtitle="Jobs, stages, tasks and shuffles">
        <ul className="space-y-2.5 text-sm text-ink-2">
          <li><b className="text-ink">FileScan parquet</b>: reads only <code>account_category</code> (column pruning, see ReadSchema) and only the
            <code> year=2016/month=10</code> folder (PartitionFilters), not the other {p.layers.silver.partitions - 1} partitions.</li>
          <li><b className="text-ink">HashAggregate (partial_count)</b>: every task counts its own rows first, like a MapReduce combiner.</li>
          <li><b className="text-ink">Exchange hashpartitioning</b>: a shuffle. Rows with the same key move to the same task, which ends one stage and starts the next.</li>
          <li><b className="text-ink">HashAggregate (count)</b>: final totals per key after the shuffle (the reduce side).</li>
          <li><b className="text-ink">AdaptiveSparkPlan</b>: adaptive query execution re-plans at runtime, for example merging small shuffle partitions.</li>
        </ul>
      </Card>
    </div>
  )
}

const VIEWS = [{ id: 'run', label: 'Pipeline run' }, { id: 'scaling', label: 'Scaling' }, { id: 'plan', label: 'Execution plan' }]

export default function SparkTab({ r }) {
  const [view, setView] = useView(VIEWS)
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'run' && <Run p={r.spark_pipeline} />}
      {view === 'scaling' && <Scaling s={r.spark_scaling} />}
      {view === 'plan' && <Plan p={r.spark_pipeline} />}
    </>
  )
}
