import { Card, Table } from '../../components/ui'
import { fmtBytes, fmtCompact, fmtInt } from '../../utils/format'
import { ViewSwitch, useView } from './shared'

function FiveVs({ r }) {
  const p = r.spark_pipeline
  const s = r.spark_scaling
  const f = r.lake_formats
  const sh = r.sharding
  const vs = [
    { v: 'Volume', q: 'How much data?', a: p
      ? `${fmtInt(p.rows.raw)} tweets in ${p.layers.raw_csv.files} CSV files (${fmtBytes(p.layers.raw_csv.bytes)}). Spark processes all of it in ${p.timings.total_sec.toFixed(0)} s; the lake keeps it in ${fmtBytes(p.layers.silver.bytes)} of partitioned Parquet${sh ? `, and ${fmtCompact(sh.params.docs)} posts are spread over ${sh.topology.shards} MongoDB shards` : ''}.`
      : '2.95M tweets, about 1.1 GB of CSV.',
      how: 'Parallel processing (Spark tasks per partition), compression and columnar storage, sharding.' },
    { v: 'Velocity', q: 'How fast does it arrive and get processed?', a: s
      ? `Batch, not streaming: the archive is processed at up to ${fmtCompact(Math.max(...s.runs.map((x) => x.rows_per_sec)))} rows/s with Spark. New uploads become visible when their ingestion job finishes; rollups are refreshed per affected day with $merge.`
      : 'Batch processing; uploads are ingested as background jobs.',
      how: 'Batch ETL, incremental $merge updates. Streaming (Kafka + Structured Streaming) is the next step and is discussed as future work.' },
    { v: 'Variety', q: 'How many shapes of data?', a: 'Semi-structured text with nested users, arrays of hashtags / mentions / URLs, 50+ languages including Cyrillic, CSV, JSON and JSONL inputs mapped onto one document model.',
      how: 'Schema-on-read in bronze, typed schema in silver, MongoDB documents with $jsonSchema validation and multikey indexes.' },
    { v: 'Veracity', q: 'Can the data be trusted?', a: p
      ? `Rows are validated (${Object.values(p.rows.invalid).reduce((a, b) => a + b, 0)} rejected), ${fmtInt(p.rows.duplicates_removed)} duplicate tweet ids removed, engagement is flagged as synthetic, sentiment is a model prediction with published accuracy, and all accounts are state-linked trolls, not a public-opinion sample.`
      : 'Validation, de-duplication, synthetic-data flags.',
      how: 'Rejection reasons, lineage columns in bronze, quality flags, honest labelling of synthetic and predicted values.' },
    { v: 'Value', q: 'What do we learn?', a: 'When the campaign was most active, which account categories drove it, which hashtags it pushed and for how long, how sentiment and topics shifted, and which days were anomalous.',
      how: f ? `Gold tables and rollups answer these in milliseconds; partitioned Parquet answers ad-hoc questions up to ${Math.max(...f.queries.map((q) => q.speedup_vs_csv))}× faster than CSV.` : 'Gold tables and rollup cubes feed the dashboard.' },
  ]
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {vs.map((x, i) => (
        <Card key={x.v} title={<span className="flex items-center gap-2"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">{i + 1}</span>{x.v}</span>} subtitle={x.q}>
          <p className="text-sm text-ink-2">{x.a}</p>
          <p className="mt-3 text-xs text-muted"><b className="text-ink-2">Techniques:</b> {x.how}</p>
        </Card>
      ))}
    </div>
  )
}

function Cap() {
  return (
    <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
      <Card title="CAP theorem" subtitle="In a network partition, choose consistency or availability">
        <svg viewBox="0 0 400 310" className="mx-auto w-full max-w-[400px]" role="img" aria-label="CAP triangle: MongoDB sits on the CP edge">
          <polygon points="200,40 50,265 350,265" fill="var(--surface-2)" stroke="var(--axis)" strokeWidth={1.5} />
          <line x1="200" y1="40" x2="350" y2="265" stroke="var(--accent)" strokeWidth={4} />
          <circle cx="200" cy="40" r="22" fill="var(--accent-soft)" stroke="var(--accent)" />
          <text x="200" y="46" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--accent)">C</text>
          <circle cx="50" cy="265" r="22" fill="var(--surface)" stroke="var(--axis)" />
          <text x="50" y="271" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--ink-2)">A</text>
          <circle cx="350" cy="265" r="22" fill="var(--accent-soft)" stroke="var(--accent)" />
          <text x="350" y="271" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--accent)">P</text>
          <text x="302" y="138" fontSize="13" fontWeight="700" fill="var(--accent)">CP</text>
          <text x="302" y="155" fontSize="11" fill="var(--ink-2)">MongoDB</text>
          <text x="302" y="169" fontSize="11" fill="var(--ink-2)">(default)</text>
          <text x="98" y="138" textAnchor="end" fontSize="13" fontWeight="700" fill="var(--ink-2)">AP</text>
          <text x="98" y="155" textAnchor="end" fontSize="11" fill="var(--ink-2)">Cassandra,</text>
          <text x="98" y="169" textAnchor="end" fontSize="11" fill="var(--ink-2)">DynamoDB</text>
          <text x="200" y="302" textAnchor="middle" fontSize="11" fill="var(--ink-2)">CA is only possible without partitions (a single node)</text>
        </svg>
        <dl className="mt-2 space-y-1.5 text-xs text-ink-2">
          <div><dt className="inline font-semibold text-ink">Consistency:</dt> <dd className="inline">every read sees the latest write.</dd></div>
          <div><dt className="inline font-semibold text-ink">Availability:</dt> <dd className="inline">every request gets a non-error answer.</dd></div>
          <div><dt className="inline font-semibold text-ink">Partition tolerance:</dt> <dd className="inline">the system keeps working when nodes cannot reach each other.</dd></div>
        </dl>
      </Card>
      <Card title="Where this project sits" subtitle="MongoDB is CP by default, tunable per operation">
        <Table rowKey={(x) => x.k} rows={[
          { k: 'Writes', v: 'Each shard is a replica set with one primary. Writes go only to the primary, so two nodes can never accept conflicting writes (consistency). If the primary is cut off, the shard refuses writes until a new primary is elected (availability is given up for seconds).' },
          { k: 'Reads', v: 'readPreference "primary" (default) gives read-your-writes consistency. "secondaryPreferred" trades that for availability and spreads load, at the risk of slightly stale data.' },
          { k: 'Write concern', v: 'w: "majority" waits until most replica-set members have the write, so it survives a failover. w: 1 is faster but can roll back. This project uses the default, majority.' },
          { k: 'Partitions in a sharded cluster', v: 'If one shard is unreachable, queries that need it fail (or return partial results with allowPartialResults), while queries targeted at healthy shards keep working. That is why the shard key matters for availability as well as speed.' },
          { k: 'Our deployment', v: 'For the experiment each shard and the config server is a one-member replica set on one machine: enough to show routing and data distribution, not fault tolerance. Production would run 3 members per replica set on separate hosts.' },
          { k: 'The data lake', v: 'Parquet files are immutable and rewritten as a whole, so readers always see a complete snapshot of a layer (consistency through write-once files, as in HDFS).' },
        ]} columns={[
          { key: 'k', label: 'Aspect', render: (x) => <span className="whitespace-nowrap font-medium text-ink">{x.k}</span> },
          { key: 'v', label: 'Behaviour', render: (x) => <span className="text-xs">{x.v}</span> },
        ]} />
      </Card>
    </div>
  )
}

const ECOSYSTEM = [
  { concept: 'Distributed file system (HDFS)', classic: 'HDFS blocks on DataNodes', here: 'Parquet lake in data/lake, partitioned folders', where: 'bigdata/spark/lake.py' },
  { concept: 'MapReduce', classic: 'map → shuffle → reduce', here: 'Spark stages: partial aggregate → Exchange (shuffle) → final aggregate; MongoDB $group', where: 'Spark tab → Execution plan' },
  { concept: 'Hive / SQL on files', classic: 'HiveQL over HDFS tables', here: 'Spark SQL DataFrames over Parquet with partition pruning', where: 'bigdata/spark/benchmarks.py' },
  { concept: 'Columnar storage', classic: 'ORC / Parquet', here: 'Parquet with snappy, gzip and zstd compared', where: 'Data lake tab → Formats' },
  { concept: 'NoSQL store', classic: 'HBase / Cassandra / MongoDB', here: 'MongoDB documents, 12 indexes, $jsonSchema', where: 'backend/app/database' },
  { concept: 'Horizontal scaling', classic: 'Region servers / partitions', here: 'MongoDB sharding with hashed and ranged keys', where: 'Sharding tab' },
  { concept: 'Pre-aggregation (OLAP cubes)', classic: 'Kylin / materialised views', here: 'Gold tables and MongoDB rollup cubes', where: 'lake.py gold_tables, analytics/rollups.py' },
  { concept: 'Batch ML', classic: 'Mahout / Spark MLlib', here: 'scikit-learn sentiment and NMF topics (batch)', where: 'backend/app/nlp' },
  { concept: 'Resource manager', classic: 'YARN', here: 'Spark local[N] scheduler (standalone/YARN/Kubernetes on a cluster)', where: 'bigdata/common.py' },
  { concept: 'Data ingestion', classic: 'Sqoop / Flume / NiFi', here: 'Spark CSV reader, Python streaming readers, upload API', where: 'lake.py, backend/app/ingestion' },
  { concept: 'Streaming', classic: 'Kafka + Spark Streaming / Flink', here: 'Not implemented (future work)', where: '–' },
]

function Ecosystem() {
  return (
    <Card title="Hadoop ecosystem map" subtitle="Each classic Big Data building block and what plays that role here">
      <Table rowKey={(x) => x.concept} rows={ECOSYSTEM} columns={[
        { key: 'concept', label: 'Concept', render: (x) => <span className="font-medium text-ink">{x.concept}</span> },
        { key: 'classic', label: 'Classic tool' },
        { key: 'here', label: 'In this project' },
        { key: 'where', label: 'Where', render: (x) => <code className="text-[11px]">{x.where}</code> },
      ]} />
    </Card>
  )
}

const VIEWS = [{ id: 'vs', label: '5 Vs' }, { id: 'cap', label: 'CAP theorem' }, { id: 'ecosystem', label: 'Hadoop ecosystem map' }]

export default function ConceptsTab({ r }) {
  const [view, setView] = useView(VIEWS)
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'vs' && <FiveVs r={r} />}
      {view === 'cap' && <Cap />}
      {view === 'ecosystem' && <Ecosystem />}
    </>
  )
}
