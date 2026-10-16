import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Async, Card, Note, Table } from '../../components/ui'
import { ChartTooltip, Legend, axisProps, gridProps } from '../../charts/common'
import { fmtBytes, fmtCompact, fmtInt, fmtMs } from '../../utils/format'
import { NotRun, RunInfo, Stat, ViewSwitch, sec, useView } from './shared'

const STRATEGY = {
  single: { label: 'Standalone (no sharding)', color: 'var(--s8)' },
  hashed: { label: 'Hashed key {post_id: "hashed"}', color: 'var(--s1)' },
  ranged: { label: 'Ranged key {created_at: 1}', color: 'var(--s3)' },
}
const SHARD_COLORS = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)']

function Topology({ s, live }) {
  const shards = s?.params.shards || ['shard1rs', 'shard2rs', 'shard3rs']
  const sx = (i) => 60 + i * 230
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <Card title="Cluster topology" subtitle="docker-compose.bigdata.yml: what runs and how a query travels">
        <div className="overflow-x-auto">
          <svg viewBox="0 0 760 400" className="min-w-[560px]" role="img" aria-label="Sharded cluster topology">
            <defs>
              <marker id="sarr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="var(--axis)" />
              </marker>
            </defs>
            <rect x={250} y={10} width={260} height={56} rx={8} fill="var(--surface)" stroke="var(--line)" />
            <text x={380} y={34} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--ink)">Application (FastAPI / Spark tasks)</text>
            <text x={380} y={52} textAnchor="middle" fontSize={11} fill="var(--ink-2)">connects only to the router</text>
            <path d="M380,66 L380,112" stroke="var(--axis)" strokeWidth={1.5} markerEnd="url(#sarr)" />
            <rect x={250} y={114} width={260} height={56} rx={8} fill="var(--accent-soft)" stroke="var(--accent)" />
            <text x={380} y={138} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--ink)">mongos router :27030</text>
            <text x={380} y={156} textAnchor="middle" fontSize={11} fill="var(--ink-2)">routes each query by shard key</text>
            <rect x={570} y={114} width={170} height={56} rx={8} fill="var(--surface)" stroke="var(--line)" strokeDasharray="4 3" />
            <text x={655} y={138} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--ink)">Config server RS</text>
            <text x={655} y={156} textAnchor="middle" fontSize={11} fill="var(--ink-2)">chunk → shard map</text>
            <path d="M510,142 L568,142" stroke="var(--axis)" strokeWidth={1.5} strokeDasharray="4 3" markerEnd="url(#sarr)" />
            {shards.map((sh, i) => {
              const d = s?.strategies.find((x) => x.name === 'hashed')?.distribution.find((x) => x.shard === sh)
              return (
                <g key={sh}>
                  <path d={`M380,170 C380,210 ${sx(i) + 90},200 ${sx(i) + 90},246`} fill="none" stroke="var(--axis)" strokeWidth={1.5} markerEnd="url(#sarr)" />
                  <rect x={sx(i)} y={248} width={180} height={110} rx={8} fill="var(--surface)" stroke={SHARD_COLORS[i]} strokeWidth={1.5} />
                  <text x={sx(i) + 90} y={272} textAnchor="middle" fontSize={13} fontWeight={600} fill="var(--ink)">{sh}</text>
                  <text x={sx(i) + 90} y={290} textAnchor="middle" fontSize={11} fill="var(--ink-2)">replica set (mongod --shardsvr)</text>
                  {d && <text x={sx(i) + 90} y={316} textAnchor="middle" fontSize={11} fill="var(--ink-2)">hashed: {fmtCompact(d.docs)} docs</text>}
                  {d && <text x={sx(i) + 90} y={334} textAnchor="middle" fontSize={11} fill="var(--ink-2)">{fmtBytes(d.bytes)} · {d.chunks ?? '–'} chunks</text>}
                </g>
              )
            })}
            <text x={380} y={392} textAnchor="middle" fontSize={11} fill="var(--ink-muted)">Each shard holds a subset of chunks; the balancer moves chunks to even out the shards.</text>
          </svg>
        </div>
      </Card>
      <Card title="Live cluster status" subtitle="/api/bigdata/cluster">
        <Async state={live} height={160}>
          {(c) => c.online ? (
            <>
              <div className="mb-3 flex items-center gap-2 text-sm"><span className="h-2 w-2 rounded-full bg-good" /> mongos online ({c.mongos})</div>
              <Table dense rowKey={(x) => x.id} rows={c.shards} columns={[
                { key: 'id', label: 'Shard', render: (x) => <code className="text-xs">{x.id}</code> },
                { key: 'host', label: 'Replica set / host', render: (x) => <code className="text-[11px]">{x.host}</code> },
              ]} />
              <p className="mt-3 text-xs text-muted">Balancer: {c.balancer}. Sharded collections: {c.sharded_collections.map((x) => x.ns).join(', ') || 'none'}</p>
            </>
          ) : (
            <div className="text-sm text-ink-2">
              <div className="mb-2 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-critical" /> Cluster not running</div>
              <p className="text-xs text-muted">{c.hint}</p>
              <p className="mt-2 text-xs text-muted">The results in the other views come from the last recorded experiment and do not need the cluster.</p>
            </div>
          )}
        </Async>
        {s && (
          <div className="mt-4 grid grid-cols-3 gap-2">
            <Stat label="Shards" value={s.topology.shards} />
            <Stat label="Routers" value={s.topology.routers} />
            <Stat label="Posts loaded" value={fmtCompact(s.params.docs)} />
          </div>
        )}
      </Card>
    </div>
  )
}

function Distribution({ s }) {
  const sharded = s.strategies.filter((x) => x.name !== 'single')
  const shards = s.params.shards
  const rows = sharded.map((st) => {
    const r = { name: STRATEGY[st.name].label }
    st.distribution.forEach((d) => { r[d.shard] = d.docs; r[`${d.shard}_chunks`] = d.chunks })
    return r
  })
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <Card title="Documents per shard" subtitle={`${fmtInt(s.params.docs)} posts in each collection`}>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid {...gridProps} horizontal={false} vertical />
            <XAxis type="number" {...axisProps} tickFormatter={fmtCompact} />
            <YAxis type="category" dataKey="name" {...axisProps} width={200} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip />} />
            {shards.map((sh, i) => <Bar key={sh} dataKey={sh} name={sh} stackId="a" fill={SHARD_COLORS[i]} barSize={28} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
        <Legend items={shards.map((sh, i) => ({ key: sh, label: sh, color: SHARD_COLORS[i] }))} />
        <Note>Ranged split points (terciles of created_at): {s.params.ranged_split_points.map((d) => String(d).slice(0, 10)).join(' and ')}.</Note>
      </Card>
      <Card title="Chunks and size" subtitle="From $collStats and config.chunks">
        <Table dense rowKey={(x) => `${x.strategy}-${x.shard}`} rows={sharded.flatMap((st) => st.distribution.map((d) => ({ ...d, strategy: st.name })))} columns={[
          { key: 'strategy', label: 'Key', render: (x) => x.strategy },
          { key: 'shard', label: 'Shard', render: (x) => <code className="text-xs">{x.shard}</code> },
          { key: 'docs', label: 'Docs', align: 'right', render: (x) => fmtInt(x.docs) },
          { key: 'share', label: 'Share', align: 'right', render: (x) => `${((100 * x.docs) / s.params.docs).toFixed(1)}%` },
          { key: 'chunks', label: 'Chunks', align: 'right', render: (x) => x.chunks ?? '–' },
        ]} />
        <Note>A hashed key spreads documents evenly without any planning. A ranged key is only even if split points follow the data; time-ordered inserts would otherwise all hit the last chunk.</Note>
      </Card>
    </div>
  )
}

function Routing({ s }) {
  const queries = s.strategies[0].queries.map((q) => q.query)
  const chart = queries.map((q) => {
    const r = { query: q }
    s.strategies.forEach((st) => { r[st.name] = st.queries.find((x) => x.query === q).median_ms })
    return r
  })
  const table = queries.map((q) => {
    const r = { query: q, description: s.strategies[0].queries.find((x) => x.query === q).description }
    s.strategies.forEach((st) => { r[st.name] = st.queries.find((x) => x.query === q) })
    return r
  })
  const cell = (x) => (
    <span className="whitespace-nowrap text-xs">
      {fmtMs(x.median_ms)} · <b className="text-ink">{x.n_shards} shard{x.n_shards === 1 ? '' : 's'}</b>
    </span>
  )
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card title="Query time by layout" subtitle={`Median of ${s.params.runs_per_query} runs`}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chart} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="query" {...axisProps} tickFormatter={(v) => v.replaceAll('_', ' ')} />
            <YAxis {...axisProps} width={52} tickFormatter={(v) => fmtMs(v)} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip valueFormatter={fmtMs} nameFormatter={(n) => STRATEGY[n]?.label || n} />} />
            {s.strategies.map((st) => <Bar key={st.name} dataKey={st.name} name={st.name} fill={STRATEGY[st.name].color} radius={[4, 4, 0, 0]} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
        <Legend items={s.strategies.map((st) => ({ key: st.name, label: STRATEGY[st.name].label, color: STRATEGY[st.name].color }))} />
      </Card>
      <Card title="Targeted vs scatter-gather" subtitle="Shards each query was sent to, from explain()">
        <Table dense rowKey={(x) => x.query} rows={table} columns={[
          { key: 'description', label: 'Query', render: (x) => <span className="text-xs">{x.description}</span> },
          ...s.strategies.filter((st) => st.name !== 'single').map((st) => ({ key: st.name, label: st.name, render: (x) => cell(x[st.name]) })),
        ]} />
        <ul className="mt-3 space-y-1.5 text-xs text-ink-2">
          <li><b className="text-ink">Targeted</b>: the filter contains the shard key, so mongos sends the query to the one shard whose chunk range matches.</li>
          <li><b className="text-ink">Scatter-gather</b>: without the shard key, mongos asks every shard and merges the answers (SHARD_MERGE).</li>
          <li>Pick the shard key that your most frequent queries filter on: date ranges favour the ranged key, lookups by id favour the hashed key.</li>
        </ul>
        <Note>{s.note}</Note>
      </Card>
    </div>
  )
}

function Loading({ s }) {
  const rows = s.strategies.map((st) => ({ name: st.name, label: STRATEGY[st.name].label, docs_per_sec: st.docs_per_sec, load_sec: st.load_sec }))
  return (
    <Card title="Bulk load through Spark" subtitle={`${fmtInt(s.params.docs)} silver posts written by parallel Spark tasks with insert_many(ordered=False)`}>
      <div className="grid gap-4 xl:grid-cols-2">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="name" {...axisProps} />
            <YAxis {...axisProps} width={48} tickFormatter={fmtCompact} />
            <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip labelFormatter={(v) => STRATEGY[v].label} />} />
            <Bar dataKey="docs_per_sec" name="Documents / s" fill="var(--s1)" radius={[4, 4, 0, 0]} isAnimationActive={false}
              label={{ position: 'top', fontSize: 11, fill: 'var(--ink-2)', formatter: fmtCompact }} />
          </BarChart>
        </ResponsiveContainer>
        <div>
          <Table dense rowKey={(x) => x.name} rows={rows} columns={[
            { key: 'label', label: 'Layout' },
            { key: 'load', label: 'Load time', align: 'right', render: (x) => sec(x.load_sec) },
            { key: 'rate', label: 'Docs / s', align: 'right', render: (x) => fmtInt(x.docs_per_sec) },
          ]} />
          <Note>Through mongos every insert batch is split by shard key and forwarded, which adds a network hop and routing work. On one machine this is overhead; with shards on separate servers the write capacity adds up.</Note>
        </div>
      </div>
    </Card>
  )
}

const VIEWS = [{ id: 'topology', label: 'Cluster' }, { id: 'distribution', label: 'Data distribution' },
  { id: 'routing', label: 'Query routing' }, { id: 'loading', label: 'Loading' }]

export default function ShardingTab({ r, live }) {
  const [view, setView] = useView(VIEWS)
  const s = r.sharding
  return (
    <>
      <ViewSwitch views={VIEWS} value={view} onChange={setView} />
      {view === 'topology' && <Topology s={s} live={live} />}
      {view !== 'topology' && !s && <NotRun cmd="python -m bigdata.sharding.experiment (needs the cluster: see docs/bigdata.md)" />}
      {view === 'distribution' && s && <Distribution s={s} />}
      {view === 'routing' && s && <Routing s={s} />}
      {view === 'loading' && s && <Loading s={s} />}
      {s && <RunInfo r={s} />}
    </>
  )
}
