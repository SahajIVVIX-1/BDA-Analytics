import { useState } from 'react'
import { Card, Table } from '../../components/ui'
import { fmtBytes, fmtInt } from '../../utils/format'
import { ViewSwitch, useView } from './shared'

const W = 176
const H = 70
const COLS = { src: 14, proc: 222, store: 430, serve: 638, ui: 846 }

// Every box on the diagram, with the detail shown when it is selected.
function nodes(r) {
  const p = r.spark_pipeline
  const s = r.sharding
  return [
    { id: 'csv', col: 'src', y: 175, title: 'Raw CSV files', sub: p ? `${p.layers.raw_csv.files} files · ${fmtBytes(p.layers.raw_csv.bytes)}` : '13 files · ~1.1 GB',
      tech: 'FiveThirtyEight russian-troll-tweets (CC BY 4.0)', path: 'data/raw/ira538/ (scripts/download_data.py)',
      text: 'The source: 2.95M tweets from accounts Twitter linked to the Internet Research Agency, 21 columns per row, 2012 to 2018. This is the volume input for both pipelines.' },
    { id: 'upload', col: 'src', y: 300, title: 'Dashboard upload', sub: 'CSV / JSON / JSONL',
      tech: 'FastAPI multipart upload', path: 'backend/app/api/ingestion.py',
      text: 'New files uploaded in the Ingestion page run through the same Python pipeline as a background job.' },
    { id: 'spark', col: 'proc', y: 40, title: 'Spark ETL', sub: 'bronze → silver → gold',
      tech: `Apache Spark ${p?.hardware?.spark || '4'} (PySpark), DataFrame API, local[*]`, path: 'bigdata/spark/lake.py, pipeline.py',
      text: 'Reads the CSV files in parallel, validates and cleans text with Spark SQL functions, removes duplicates with a shuffle on post_id, partitions by year/month and builds gold aggregates. Same code runs on a cluster by changing the master URL.' },
    { id: 'py', col: 'proc', y: 175, title: 'Python ingestion', sub: 'clean · validate · bulk insert',
      tech: 'Python multiprocessing + PyMongo insert_many', path: 'backend/app/ingestion/',
      text: 'The original pipeline: streams rows, cleans them in a process pool and bulk-inserts batches of 5,000 into MongoDB.' },
    { id: 'nlp', col: 'proc', y: 300, title: 'NLP enrichment', sub: 'sentiment · topics · keywords',
      tech: 'scikit-learn (TF-IDF + logistic regression, NMF)', path: 'backend/app/nlp/',
      text: 'Reads unprocessed posts through a partial index and writes sentiment, topic and keywords back with bulk updates.' },
    { id: 'loader', col: 'proc', y: 430, title: 'Spark → MongoDB loader', sub: 'foreachPartition writes',
      tech: 'Spark tasks + PyMongo, one writer per partition', path: 'bigdata/sharding/experiment.py',
      text: 'Loads silver posts into the sharded cluster. Each Spark partition is written by its own task through the mongos router, so writes run in parallel.' },
    { id: 'lake', col: 'store', y: 40, title: 'Data lake (Parquet)', sub: p ? `${fmtBytes(p.layers.bronze.bytes + p.layers.silver.bytes + p.layers.gold.bytes)} in 3 layers` : 'bronze · silver · gold',
      tech: 'Apache Parquet, snappy compression, Hive-style partitions', path: 'data/lake/{bronze,silver,gold}',
      text: 'Columnar files: queries read only the columns and partitions they need. Bronze keeps raw rows, silver holds cleaned posts partitioned by year/month, gold holds small aggregate tables.' },
    { id: 'mongo', col: 'store', y: 175, title: 'MongoDB (single node)', sub: 'posts + 12 indexes + rollups',
      tech: 'MongoDB 8, $jsonSchema validation, aggregation pipelines', path: 'backend/app/database/, analytics/rollups.py',
      text: 'System of record for the dashboard. Aggregation pipelines ($group, $unwind, $merge, $out) build the daily/hourly cubes and hashtag/keyword rollups.' },
    { id: 'rollup', col: 'store', y: 300, title: 'Rollup collections', sub: 'daily / hourly cubes',
      tech: 'MongoDB aggregation pipelines → $out / $merge', path: 'backend/app/analytics/rollups.py',
      text: 'Pre-aggregated cubes so dashboard charts read ~130K rows instead of 2.9M posts.' },
    { id: 'shard', col: 'store', y: 430, title: 'Sharded cluster', sub: s ? `mongos + ${s.topology.shards} shards` : 'mongos + 3 shards',
      tech: 'MongoDB sharding: config server replica set, 3 shard replica sets, mongos router', path: 'docker-compose.bigdata.yml, bigdata/sharding/',
      text: 'Horizontal scaling: the posts collection is split into chunks by a shard key and spread over three shards. mongos routes each query to only the shards that hold matching data.' },
    { id: 'results', col: 'serve', y: 40, title: 'Experiment results', sub: 'measured JSON',
      tech: 'JSON written by every experiment', path: 'experiments/results/*.json',
      text: 'Every number on the Performance and Big Data Lab pages comes from these files, written when an experiment runs, with the hardware it ran on.' },
    { id: 'api', col: 'serve', y: 240, title: 'FastAPI', sub: 'REST API · query planner',
      tech: 'FastAPI + Pydantic, gzip, in-process TTL cache', path: 'backend/app/api/',
      text: 'Serves analytics (cube or live query planner), posts, ingestion jobs, performance results and the Big Data Lab endpoints (/api/bigdata/*).' },
    { id: 'ui', col: 'ui', y: 240, title: 'React dashboard', sub: 'charts · tabs · filters',
      tech: 'React 19, Vite, Tailwind, Recharts', path: 'frontend/',
      text: 'This app. Filters and tabs live in the URL so every view can be bookmarked.' },
  ]
}

const EDGES = [
  ['csv', 'spark'], ['spark', 'lake'], ['spark', 'results'], ['lake', 'loader'], ['loader', 'shard'],
  ['csv', 'py'], ['upload', 'py'], ['py', 'mongo'], ['mongo', 'nlp', -10], ['nlp', 'mongo', 10], ['mongo', 'rollup'],
  ['mongo', 'api'], ['rollup', 'api'], ['lake', 'api'], ['results', 'api'], ['shard', 'api'], ['api', 'ui'],
]

function edgePath(a, b, dy = 0) {
  const ax = COLS[a.col], bx = COLS[b.col]
  if (ax === bx) {  // same column: bottom to top
    const x = ax + W / 2
    return `M${x},${a.y + H} L${x},${b.y}`
  }
  const fwd = bx > ax
  const x1 = fwd ? ax + W : ax
  const x2 = fwd ? bx : bx + W
  const y1 = a.y + H / 2 + dy
  const y2 = b.y + H / 2 + dy
  const mx = (x1 + x2) / 2
  return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`
}

function Diagram({ r }) {
  const list = nodes(r)
  const byId = Object.fromEntries(list.map((n) => [n.id, n]))
  const [sel, setSel] = useState('spark')
  const s = byId[sel]
  const linked = new Set(EDGES.filter(([a, b]) => a === sel || b === sel).flatMap(([a, b]) => [a, b]))
  const lanes = [['src', 'Sources'], ['proc', 'Processing'], ['store', 'Storage'], ['serve', 'Serving'], ['ui', 'Presentation']]
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
      <Card title="End-to-end data flow" subtitle="Select a box to see what it does, the technology and where the code is">
        <div className="overflow-x-auto">
          <svg viewBox="0 0 1036 530" className="min-w-[720px]" role="img" aria-label="Architecture diagram of the data flow">
            <defs>
              <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="var(--axis)" />
              </marker>
              <marker id="arr-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
              </marker>
            </defs>
            {lanes.map(([k, label]) => (
              <g key={k}>
                <rect x={COLS[k] - 10} y={8} width={W + 20} height={512} rx={10} fill="var(--surface-2)" opacity={0.6} />
                <text x={COLS[k] + W / 2} y={26} textAnchor="middle" fontSize={11} fill="var(--ink-muted)" fontWeight={600}>{label.toUpperCase()}</text>
              </g>
            ))}
            {EDGES.map(([a, b, dy]) => {
              const on = a === sel || b === sel
              return <path key={`${a}-${b}`} d={edgePath(byId[a], byId[b], dy)} fill="none" strokeWidth={on ? 2 : 1.3}
                stroke={on ? 'var(--accent)' : 'var(--axis)'} markerEnd={`url(#${on ? 'arr-on' : 'arr'})`} />
            })}
            {list.map((n) => {
              const x = COLS[n.col]
              const active = n.id === sel
              const dim = sel && !active && !linked.has(n.id)
              return (
                <g key={n.id} onClick={() => setSel(n.id)} style={{ cursor: 'pointer' }} opacity={dim ? 0.55 : 1}
                  role="button" tabIndex={0} aria-label={n.title} onKeyDown={(e) => e.key === 'Enter' && setSel(n.id)}>
                  <rect x={x} y={n.y} width={W} height={H} rx={8} fill="var(--surface)"
                    stroke={active ? 'var(--accent)' : 'var(--line)'} strokeWidth={active ? 2 : 1} />
                  <text x={x + 10} y={n.y + 29} fontSize={14} fontWeight={600} fill="var(--ink)">{n.title}</text>
                  <text x={x + 10} y={n.y + 50} fontSize={12} fill="var(--ink-2)">{n.sub}</text>
                </g>
              )
            })}
          </svg>
        </div>
      </Card>
      <Card title={s.title} subtitle={s.sub}>
        <dl className="space-y-3 text-sm">
          <div><dt className="text-xs text-muted">What it does</dt><dd className="mt-0.5 text-ink-2">{s.text}</dd></div>
          <div><dt className="text-xs text-muted">Technology</dt><dd className="mt-0.5 text-ink-2">{s.tech}</dd></div>
          <div><dt className="text-xs text-muted">Code / location</dt><dd className="mt-0.5"><code className="text-xs text-ink">{s.path}</code></dd></div>
          <div>
            <dt className="text-xs text-muted">Connected to</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {[...linked].filter((x) => x !== sel).map((x) => (
                <button key={x} onClick={() => setSel(x)} className="rounded-full border border-line px-2 py-0.5 text-xs text-ink-2 hover:bg-surface-2">{byId[x].title}</button>
              ))}
            </dd>
          </div>
        </dl>
      </Card>
    </div>
  )
}

function Steps({ r }) {
  const p = r.spark_pipeline
  const s = r.sharding
  const steps = [
    ['1', 'Collect', 'scripts/download_data.py', `Download 13 CSV files${p ? ` (${fmtBytes(p.layers.raw_csv.bytes)}, ${fmtInt(p.rows.raw)} rows)` : ''} into data/raw/ira538.`],
    ['2', 'Bronze', 'bigdata/spark/lake.py · build_bronze', `Spark reads all files in parallel with a fixed all-string schema and stores them as Parquet with the source file name and load time${p ? ` (${fmtBytes(p.layers.bronze.bytes)}, ${p.layers.bronze.files} files)` : ''}.`],
    ['3', 'Validate', 'lake.py · validity', `Each row gets a rejection reason or none: missing id, empty text, bad timestamp${p ? `. Rejected: ${Object.entries(p.rows.invalid).map(([k, v]) => `${v} ${k}`).join(', ') || 'none'}` : ''}.`],
    ['4', 'Silver', 'lake.py · to_silver', `Clean text, extract hashtags / mentions / URLs with regular expressions, map languages to ISO codes, drop duplicate tweet ids (${p ? fmtInt(p.rows.duplicates_removed) : '…'} removed), partition by year and month${p ? ` (${p.layers.silver.partitions} partitions)` : ''}.`],
    ['5', 'Gold', 'lake.py · gold_tables', 'Group and aggregate silver into five tables: daily activity cube, hashtag per day, top hashtags, account statistics, monthly posts per account category.'],
    ['6', 'Serve (single node)', 'backend/app/ingestion, analytics', 'The original Python pipeline loads MongoDB, runs NLP and builds rollup cubes the dashboard reads.'],
    ['7', 'Scale out (sharded)', 'bigdata/sharding', `Spark loads silver posts into a sharded cluster${s ? ` (${fmtInt(s.params.docs)} posts, ${s.topology.shards} shards)` : ''} and the experiment compares hashed and ranged shard keys.`],
    ['8', 'Measure', 'bigdata/spark/benchmarks.py, experiments/', 'Scaling, formats, partition pruning and sharding experiments write JSON results with the hardware they ran on.'],
    ['9', 'Present', 'frontend/', 'FastAPI serves results and analytics; this dashboard shows them in tabs.'],
  ]
  return (
    <Card title="Data flow, step by step" subtitle="From raw files to the charts on this page">
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {steps.map(([n, t, path, text]) => (
          <li key={n} className="flex gap-3 rounded-lg border border-line p-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">{n}</span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">{t}</p>
              <code className="text-[11px] text-muted">{path}</code>
              <p className="mt-1 text-xs text-ink-2">{text}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

const STACK = [
  { layer: 'Distributed processing', tech: 'Apache Spark 4 (PySpark)', why: 'Parallel ETL over partitions; same code scales from a laptop to a cluster' },
  { layer: 'Storage format', tech: 'Apache Parquet + snappy', why: 'Columnar, compressed, splittable; supports partition pruning and column pruning' },
  { layer: 'Data lake layout', tech: 'Medallion: bronze / silver / gold', why: 'Raw data is kept, cleaning is repeatable, aggregates are cheap to serve' },
  { layer: 'Operational database', tech: 'MongoDB 8', why: 'Flexible documents, multikey indexes on arrays, aggregation framework' },
  { layer: 'Horizontal scaling', tech: 'MongoDB sharding (config RS, 3 shard RS, mongos)', why: 'Splits a collection across machines by a shard key' },
  { layer: 'Batch NLP', tech: 'scikit-learn', why: 'CPU-only sentiment and topic models' },
  { layer: 'API', tech: 'FastAPI + Pydantic', why: 'Typed REST endpoints, OpenAPI docs at /docs' },
  { layer: 'Dashboard', tech: 'React 19 + Vite + Tailwind + Recharts', why: 'Lazy-loaded pages, URL state, dark mode' },
  { layer: 'Containers', tech: 'Docker Compose', why: 'One command starts Spark and the sharded cluster with no local Java or MongoDB install' },
]

function Stack() {
  return (
    <Card title="Technology stack" subtitle="What each Big Data component is and why it was chosen">
      <Table rowKey={(x) => x.layer} rows={STACK} columns={[
        { key: 'layer', label: 'Layer', render: (x) => <span className="font-medium text-ink">{x.layer}</span> },
        { key: 'tech', label: 'Technology' },
        { key: 'why', label: 'Why' },
      ]} />
    </Card>
  )
}

const VIEWS = [{ id: 'diagram', label: 'Diagram' }, { id: 'steps', label: 'Step by step' }, { id: 'stack', label: 'Tech stack' }]

export default function Architecture({ r }) {
  const [view, setView] = useView(VIEWS)
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'diagram' && <Diagram r={r} />}
      {view === 'steps' && <Steps r={r} />}
      {view === 'stack' && <Stack />}
    </>
  )
}
