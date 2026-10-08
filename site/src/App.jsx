import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  REPO, aggregationOps, blob, codeLinks, collections, headline, indexVsScan, indexes, ingestionScaling,
  datasetSource, datasetFields, ingestionStats, nlpThroughput, postsPerYear, qualityFlags, rollupVsLive, screens, sentimentMix, sentimentModels,
  sentimentPipelineScaling, tree, trendExample, workers,
} from './data.js'

const NAV = [
  ['overview', 'Overview'],
  ['architecture', 'Architecture'],
  ['dataset', 'About Dataset'],
  ['mongodb', 'MongoDB'],
  ['methods', 'Methods'],
  ['results', 'Results'],
  ['dashboard', 'Dashboard'],
  ['code', 'Code'],
]

const BASE = import.meta.env.BASE_URL
const fmt = (n) => n.toLocaleString('en-US')

function useDarkMode() {
  const query = '(prefers-color-scheme: dark)'
  const [dark, setDark] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = (e) => setDark(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return dark
}

function useActiveSection() {
  const [active, setActive] = useState('overview')
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: '-45% 0px -50% 0px' },
    )
    NAV.forEach(([id]) => { const el = document.getElementById(id); if (el) obs.observe(el) })
    return () => obs.disconnect()
  }, [])
  return active
}

function chartTheme(dark) {
  return dark
    ? { grid: '#3a3936', axis: '#a8a49b', tip: '#262624', tipBorder: '#3a3936', text: '#ece9e1' }
    : { grid: '#e6e2d8', axis: '#6b675f', tip: '#ffffff', tipBorder: '#e6e2d8', text: '#1f1e1c' }
}

const C = { clay: '#d97757', slate: '#5b7c99', olive: '#7f9a5a', sand: '#c9a961' }

function Section({ id, eyebrow, title, intro, children }) {
  return (
    <section id={id} className="section">
      <div className="section-head">
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {intro && <p className="lede">{intro}</p>}
      </div>
      {children}
    </section>
  )
}

function Card({ title, source, children, className = '' }) {
  return (
    <figure className={`card ${className}`}>
      {title && <figcaption className="card-title">{title}</figcaption>}
      {children}
      {source && <p className="source">Source: <a href={blob(source)}>{source}</a></p>}
    </figure>
  )
}

function Badge({ children, tone = 'warn' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

function Tip({ t }) {
  return {
    contentStyle: { background: t.tip, border: `1px solid ${t.tipBorder}`, borderRadius: 10, color: t.text, fontSize: 13 },
    labelStyle: { color: t.text, fontWeight: 600 },
    cursor: { fill: 'rgba(127,127,127,0.08)' },
  }
}

function Header({ active }) {
  const [open, setOpen] = useState(false)
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <a href="#overview" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark" aria-hidden="true">◆</span> BDA Analytics
        </a>
        <button className="menu-btn" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>
          {open ? 'Close' : 'Menu'}
        </button>
        <nav id="nav" className={open ? 'open' : ''} aria-label="Sections">
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={active === id ? 'active' : ''} onClick={() => setOpen(false)}>{label}</a>
          ))}
          <a href={REPO} className="gh">GitHub ↗</a>
        </nav>
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section id="overview" className="hero">
      <p className="eyebrow">Big Data Analytics · University project</p>
      <h1>
        Large-scale social media sentiment and trend analytics, <em>built on MongoDB</em>
      </h1>
      <p className="hero-lede">
        Almost three million real tweets streamed, cleaned and bulk-loaded into MongoDB, enriched with lightweight
        NLP, pre-aggregated with aggregation pipelines, served by FastAPI and explored in a React dashboard. All of
        it on one 16&nbsp;GB machine with no GPU, no Spark and no cluster.
      </p>
      <div className="hero-actions">
        <a className="btn btn-primary" href={REPO}>View the code</a>
        <a className="btn" href={blob('docs/report.md')}>Read the report</a>
        <a className="btn" href="#results">See the results</a>
      </div>
      <div className="stats">
        {headline.map((s) => (
          <div key={s.label} className="stat">
            <div className="stat-value">{s.value}</div>
            <div className="stat-label">{s.label}</div>
          </div>
        ))}
      </div>
      <figure className="hero-shot">
        <img src={`${BASE}screens/overview.png`} alt="Overview page of the React analytics dashboard" />
      </figure>
    </section>
  )
}

function Architecture() {
  const steps = [
    ['CSV · JSON · JSONL', 'Raw files, optionally gzipped'],
    ['Streaming readers', 'Never loads the whole file into RAM'],
    ['Cleaning pool', 'Validate, normalise, extract entities, flag quality'],
    ['Bulk insert', 'Batches of 5,000, duplicates rejected by the unique index'],
    ['MongoDB posts', 'Schema-validated, 12 indexes'],
    ['NLP enrichment', 'Sentiment, topic, keywords written back'],
    ['Aggregation → rollups', 'daily, hourly, hashtag, keyword, users'],
    ['FastAPI', 'Query planner: rollup when possible, live otherwise'],
    ['React dashboard', '10 pages, filters in the URL'],
  ]
  const stack = [
    ['Database', 'MongoDB 8.0.23 Community, WiredTiger'],
    ['Driver', 'PyMongo 4.18'],
    ['Backend', 'Python 3.13, FastAPI 0.142, Pydantic 2.13, Uvicorn'],
    ['NLP / ML', 'scikit-learn 1.9, vaderSentiment 3.3.2, NumPy 2.5'],
    ['Reporting', 'pandas 3.0'],
    ['Frontend', 'React 19, Vite 8, Tailwind CSS 4, Recharts 3, React Router 7'],
    ['Testing', 'pytest 9, Vitest 5, Testing Library, ruff, oxlint'],
  ]
  return (
    <Section
      id="architecture"
      eyebrow="Architecture"
      title="A layered batch pipeline with MongoDB at the centre"
      intro="MongoDB is both the system of record and the main computation engine. Processing is batch-oriented and parallel within one machine; dashboard queries read pre-aggregated rollups whenever the filters allow."
    >
      <ol className="flow">
        {steps.map(([name, desc], i) => (
          <li key={name} className={name.startsWith('MongoDB') ? 'flow-db' : ''}>
            <span className="flow-n">{String(i + 1).padStart(2, '0')}</span>
            <strong>{name}</strong>
            <span>{desc}</span>
          </li>
        ))}
      </ol>
      <div className="grid-2">
        <Card title="Technology stack" source="docs/report.md">
          <dl className="kv">
            {stack.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
          </dl>
        </Card>
        <Card title="Deliberately not used">
          <ul className="plain">
            <li><strong>Spark / PySpark, Streamlit</strong>: excluded by the course brief.</li>
            <li><strong>Distributed processing</strong>: one <code>mongod</code>, no sharding or replica set.</li>
            <li><strong>Real-time streaming</strong>: data arrives through batch ingestion jobs.</li>
            <li><strong>Transformers and GPUs</strong>: scikit-learn models so everything runs on a CPU.</li>
            <li><strong>A 5M experiment</strong>: the real dataset has 2.95M posts and was not padded with synthetic posts.</li>
          </ul>
        </Card>
      </div>
    </Section>
  )
}

function Dataset({ t }) {
  return (
    <Section
      id="dataset"
      eyebrow="About Dataset"
      title="Real tweets, described honestly"
      intro="FiveThirtyEight's russian-troll-tweets dataset: tweets from accounts Twitter linked to the Internet Research Agency, collected by Linvill and Warren at Clemson University and published under CC BY 4.0."
    >
      <div className="facts">
        <div><span className="fact-v">2,946,207</span><span className="fact-l">rows read</span></div>
        <div><span className="fact-v">2,944,814</span><span className="fact-l">posts stored</span></div>
        <div><span className="fact-v">2,843</span><span className="fact-l">accounts</span></div>
        <div><span className="fact-v">2012 – 2018</span><span className="fact-l">99.5% in 2015–2017</span></div>
        <div><span className="fact-v">56</span><span className="fact-l">language values</span></div>
        <div><span className="fact-v">80.6%</span><span className="fact-l">posts with a country</span></div>
      </div>

      <div className="grid-2">
        <Card title="Source" source="docs/dataset.md">
          <dl className="kv">
            {datasetSource.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v.startsWith('https://') ? <a href={v}>{v.replace('https://github.com/', '')}</a> : v}</dd></div>))}
          </dl>
        </Card>
        <Card title="Posts per year" source="docs/dataset.md">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={postsPerYear} margin={{ top: 8, right: 8, left: 4 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="year" stroke={t.axis} fontSize={12} />
              <YAxis stroke={t.axis} fontSize={12} tickFormatter={(v) => `${v / 1000}K`} />
              <Tooltip {...Tip({ t })} formatter={(v) => [fmt(v), 'posts']} />
              <Bar dataKey="posts" fill={C.slate} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="note">Busiest day: 2016-10-06 with 18,634 posts. Collection gap from about 2017-10-23 to 2017-11-06. 44% of posts are retweets.</p>
        </Card>
      </div>

      <div className="callouts">
        <div className="callout callout-warn">
          <Badge>Synthetic data</Badge>
          <h3>Engagement is synthetic</h3>
          <p>
            The source has no like, reply or retweet counts. To exercise the engagement module,
            <code> scripts/synthesize_engagement.py</code> generates them deterministically from each author's real
            follower count. Every value is stored with <code>engagement.synthetic = true</code> and every engagement
            chart in the dashboard carries a badge. They say nothing about real audiences.
          </p>
          <pre className="code">{`base     = 0.004 × followers^0.85   (× 0.1 for retweets)
likes    = floor(base × LogNormal(0, 1.1))
shares   = Binomial(likes, Uniform(0.10, 0.35))
comments = Binomial(likes, Uniform(0.02, 0.12))
total    = likes + comments + shares`}</pre>
        </div>
        <div className="callout">
          <Badge tone="info">Not representative</Badge>
          <h3>A troll-account archive, not public opinion</h3>
          <p>
            Every account is a state-linked troll account, so results describe that campaign. Sentiment is a model
            prediction for English posts only; non-English posts are counted as <code>not_analyzed</code>. Location is
            the account-level region (country only). Time zone is assumed to be UTC.
          </p>
        </div>
      </div>

      <div className="grid-2">
        <Card title="Full ingestion run" source="docs/report.md">
          <table className="table compact">
            <tbody>
              {ingestionStats.map(([k, v]) => (<tr key={k}><th scope="row">{k}</th><td className="num">{v}</td></tr>))}
            </tbody>
          </table>
        </Card>
        <Card title="Posts flagged by the cleaning step" source="docs/report.md">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={qualityFlags} layout="vertical" margin={{ left: 8, right: 24 }}>
              <CartesianGrid horizontal={false} stroke={t.grid} />
              <XAxis type="number" tickFormatter={(v) => `${v / 1000}K`} stroke={t.axis} fontSize={12} />
              <YAxis type="category" dataKey="flag" width={118} stroke={t.axis} fontSize={12} />
              <Tooltip {...Tip({ t })} formatter={(v) => [fmt(v), 'posts']} />
              <Bar dataKey="count" fill={C.sand} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="note">Flags are kept on the document as <code>quality_flags</code> rather than deleting posts.</p>
        </Card>
      </div>

      <Card title="Fields and how they are stored" source="docs/dataset.md" className="wide">
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Source column</th><th>Stored as</th><th>Notes</th></tr></thead>
            <tbody>
              {datasetFields.map(([a, b, n]) => (<tr key={a}><td><code>{a}</code></td><td><code>{b}</code></td><td>{n || '—'}</td></tr>))}
            </tbody>
          </table>
        </div>
        <p className="note">
          Sentiment was trained and evaluated on a separate dataset, TweetEval (train 45,615 / validation 2,000 / test 12,284),
          which is never stored in MongoDB. Raw data is downloaded by <code>scripts/download_data.py</code> and is not in the repository.
        </p>
      </Card>
    </Section>
  )
}

function MongoDesign() {
  return (
    <Section
      id="mongodb"
      eyebrow="MongoDB design"
      title="Documents, indexes and pipelines chosen per query"
      intro="Fields the analytics filter on are embedded in each post so no query needs a join. Hashtags, mentions and keywords are arrays indexed as multikey. A $jsonSchema validator with validationAction: error rejects malformed documents at the server."
    >
      <div className="grid-2">
        <Card title="A real document from the posts collection" source="docs/database.md">
          <pre className="code code-tall">{`{
  "post_id": "505180048811622400",
  "text": "The way she climbs up and down them poles #love #rap",
  "clean_text": "The way she climbs up and down them poles love rap",
  "created_at": ISODate("2014-08-29T02:28:00Z"),
  "language": "en",
  "location": { "country": "United States", "city": null },
  "user": { "username": "IRIS0_O", "followers": 2693, ... },
  "hashtags": ["love", "rap"],
  "engagement": { "likes": 0, "total": 0, "synthetic": true },
  "sentiment": { "label": "positive", "score": 0.8046,
                 "confidence": 0.8904, "method": "tfidf_logreg" },
  "topic": { "id": "en-07", "label": "Love / Hate / Lost",
             "weight": 0.0854, "method": "tfidf_nmf" },
  "keywords": ["climbs", "love rap", "rap", "love"],
  "quality_flags": [],
  "processed": true
}`}</pre>
        </Card>
        <Card title="Collections" source="docs/database.md">
          <table className="table compact">
            <thead><tr><th>Collection</th><th className="num">Documents</th></tr></thead>
            <tbody>
              {collections.map((c) => (
                <tr key={c.name}><th scope="row"><code>{c.name}</code><span className="sub">{c.purpose}</span></th><td className="num">{c.docs}</td></tr>
              ))}
            </tbody>
          </table>
          <p className="note"><code>posts</code>: 3.50 GB uncompressed BSON, 1.11 GB on disk with WiredTiger compression, 0.98 GB of indexes.</p>
        </Card>
      </div>

      <Card title="The 12 indexes on posts, and why each exists" source="backend/app/database/indexes.py" className="wide">
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Name</th><th>Keys</th><th>Options</th><th>Why</th></tr></thead>
            <tbody>
              {indexes.map(([n, k, o, w]) => (
                <tr key={n}><td><code>{n}</code></td><td><code>{k}</code></td><td>{o || '—'}</td><td>{w}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          Compound indexes follow the <strong>equality, sort, range</strong> rule, so one index serves “negative posts in
          October 2016, newest first”. Low-cardinality fields such as <code>is_retweet</code> are deliberately not indexed.
        </p>
      </Card>

      <div className="grid-2">
        <Card title="Aggregation operators used">
          <div className="chips">{aggregationOps.map((o) => <code key={o} className="chip">{o}</code>)}</div>
          <p className="note">Every statistic shown in the dashboard is computed by MongoDB. Rollups are written with <code>$merge</code> and refreshed only for the days affected by a new upload.</p>
        </Card>
        <Card title="Checking that an index is used" source="docs/database.md">
          <pre className="code">{`db.posts.find({
  "sentiment.label": "negative",
  created_at: { $gte: ISODate("2016-10-01"),
                $lt:  ISODate("2016-11-01") }
}).explain("executionStats")`}</pre>
          <p className="note">The dashboard's Performance page runs such queries live through <code>GET /api/performance/explain/{'{name}'}</code>.</p>
        </Card>
      </div>
    </Section>
  )
}

function Methods({ t }) {
  return (
    <Section
      id="methods"
      eyebrow="Methodology"
      title="Sentiment, topics, trends and anomalies"
      intro="Lightweight, CPU-only methods chosen for accuracy per second on a laptop, each evaluated or documented with its limits."
    >
      <div className="grid-2">
        <Card title="Sentiment: three models on the TweetEval test split (12,284 tweets)" source="experiments/results/sentiment_evaluation.json">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={sentimentModels} margin={{ top: 8, right: 8, left: -12 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="model" stroke={t.axis} fontSize={11} interval={0} tickFormatter={(v) => v.replace('TF-IDF + ', '')} />
              <YAxis domain={[0, 0.7]} stroke={t.axis} fontSize={12} />
              <Tooltip {...Tip({ t })} formatter={(v) => v.toFixed(3)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="f1" name="Macro-F1" fill={C.clay} radius={[4, 4, 0, 0]} />
              <Bar dataKey="acc" name="Accuracy" fill={C.slate} radius={[4, 4, 0, 0]} />
              <Bar dataKey="recall" name="Macro recall" fill={C.olive} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="note">
            Logistic regression was selected by validation macro-F1 (0.650 vs 0.560 VADER, 0.506 Naive Bayes) and scores
            0.582 test macro-F1. That is below TweetEval's published baselines; accuracy on the IRA tweets themselves has not been measured.
          </p>
        </Card>
        <Card title="Predicted sentiment of 2,111,943 English posts" source="docs/report.md">
          <div className="mix">
            {sentimentMix.map((s) => (
              <div key={s.label} className={`mix-seg mix-${s.label.toLowerCase()}`} style={{ flexBasis: `${s.share}%` }}>
                <span>{s.label}</span><strong>{s.share}%</strong>
              </div>
            ))}
          </div>
          <p className="note">Model outputs on out-of-domain text, not measured truth.</p>
          <h4 className="mini-h">Topics</h4>
          <p>
            TF-IDF (1–2 grams) with non-negative matrix factorisation, one model per language trained on 200,000 sampled
            posts: <strong>16 English</strong> and <strong>12 Russian</strong> topics, labelled by top terms such as
            “Trump / Donald / Donald Trump” and “Police / Shooting / Local”. A post gets its strongest topic if the weight
            is at least 0.02; 66% of English and 75% of Russian posts fall below that and are reported as unassigned.
          </p>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Trend score" source="docs/methodology.md">
          <pre className="code">{`trend score = log10(1 + now)
            × log2((now + 5) / (before + 5))
            × (1 + 0.1 × log10(1 + avg reach))`}</pre>
          <p>
            Window-over-window comparison over the daily hashtag, keyword and topic rollups, with growth % and share growth %.
            A warning is raised when total volume changes more than threefold between windows.
          </p>
          <p className="note">
            Week ending 2016-11-08: <code>#trumpforpresident</code> rose from 1 to 1,682 posts (score 34.8), followed by{' '}
            {trendExample.slice(1).map((h, i) => <span key={h}><code>{h}</code>{i < 3 ? ', ' : '.'}</span>)}
          </p>
        </Card>
        <Card title="Anomaly detection" source="docs/methodology.md">
          <ul className="plain">
            <li><strong>Rolling z-score</strong> over the previous 28 days, computed in MongoDB with <code>$setWindowFields</code>, for volume and negative share; at least 100 posts.</li>
            <li><strong>IQR rule</strong> on daily posts over the selected period.</li>
            <li><strong>Isolation Forest</strong> (200 trees, contamination 0.02) on log posts, negative share, retweet share and log mean reach.</li>
          </ul>
          <p className="note">
            With |z| ≥ 3, 128 of 1,699 days are flagged by at least one method. The largest spike, 2016-10-06, had 18,634
            posts against an expected 3,483 (z = 7.1).
          </p>
        </Card>
      </div>
    </Section>
  )
}

function Results({ t }) {
  return (
    <Section
      id="results"
      eyebrow="Measured results"
      title="Performance experiments at 100K, 500K, 1M and 2.94M posts"
      intro="Measured on one cloud VM (Intel Xeon @ 2.80 GHz, 4 vCPUs, 15.7 GB RAM, MongoDB 8.0.23 with a 4 GB WiredTiger cache, Python 3.13) on 2026-10-08. Timings are medians of three runs unless stated."
    >
      <div className="grid-2">
        <Card title="Ingestion scales linearly" source="experiments/results/ingestion_scaling.json">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={ingestionScaling} margin={{ top: 8, right: 8, left: -12 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="posts" stroke={t.axis} fontSize={12} />
              <YAxis stroke={t.axis} fontSize={12} unit="s" />
              <Tooltip {...Tip({ t })} formatter={(v) => `${v} s`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="load" name="Load" stackId="a" fill={C.clay} />
              <Bar dataKey="index" name="Index build" stackId="a" fill={C.slate} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="note">Throughput stayed between 9,917 and 11,815 records/s. Full load: 297 s plus 311 s of index build.</p>
        </Card>
        <Card title="Parallel cleaning workers (records/s)" source="experiments/results/ingestion_workers.json">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={workers} margin={{ top: 8, right: 8, left: 0 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="workers" stroke={t.axis} fontSize={12} />
              <YAxis stroke={t.axis} fontSize={12} tickFormatter={(v) => `${v / 1000}K`} />
              <Tooltip {...Tip({ t })} formatter={(v) => [fmt(v), 'records/s']} />
              <Bar dataKey="rate" fill={C.olive} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="note">
            Two workers were best on 4 vCPUs shared with the inserting process and <code>mongod</code>. Batches of 100 gave
            7,909 records/s; 500 to 20,000 gave 11,184–11,795. Building indexes after the load saved 16% (57.3 s vs 68.1 s).
          </p>
        </Card>
      </div>

      <Card title="Indexed query vs collection scan on 2.94M posts (ms, log scale)" source="experiments/results/index_vs_collscan.json" className="wide">
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={indexVsScan} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid horizontal={false} stroke={t.grid} />
            <XAxis type="number" scale="log" domain={[0.5, 10000]} ticks={[1, 10, 100, 1000, 10000]} allowDataOverflow stroke={t.axis} fontSize={12} />
            <YAxis type="category" dataKey="query" width={190} stroke={t.axis} fontSize={12} />
            <Tooltip {...Tip({ t })} formatter={(v, name, p) => [name === 'Indexed' && p.payload.indexedLabel ? `${p.payload.indexedLabel} ms` : `${fmt(v)} ms`, name]} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="scan" name="Collection scan" fill={C.sand} radius={[0, 4, 4, 0]} />
            <Bar dataKey="indexed" name="Indexed" fill={C.clay} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="table-scroll">
          <table className="table compact">
            <thead><tr><th>Query</th><th className="num">Scan (ms)</th><th className="num">Indexed (ms)</th><th className="num">Docs examined with index</th></tr></thead>
            <tbody>
              {indexVsScan.map((r) => (
                <tr key={r.query}><td>{r.query}</td><td className="num">{fmt(r.scan)}</td><td className="num">{r.indexedLabel || fmt(r.indexed)}</td><td className="num">{r.examined}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">A collection scan examined all 2,944,814 documents. With the matching index each query examined only the documents it returned.</p>
      </Card>

      <div className="grid-2">
        <Card title="Pre-aggregation: live on posts vs from the daily_cube rollup (s)" source="experiments/results/aggregation_scaling.json">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={rollupVsLive} margin={{ top: 8, right: 8, left: -12 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="query" stroke={t.axis} fontSize={11} interval={0} tickFormatter={(v) => v.replace(' page', '').replace('Overview, ', '')} />
              <YAxis stroke={t.axis} fontSize={12} unit="s" />
              <Tooltip {...Tip({ t })} formatter={(v) => `${v} s`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="live" name="Live on posts" fill={C.sand} radius={[4, 4, 0, 0]} />
              <Bar dataKey="rollup" name="From rollup" fill={C.clay} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="chips">{rollupVsLive.map((r) => <span key={r.query} className="chip chip-strong">{r.query}: {r.speedup}</span>)}</div>
          <p className="note">The price: 470 s for a full rebuild of all five rollups, 333 s of it for the 4.4M-row keyword rollup.</p>
        </Card>
        <Card title="Sentiment-distribution pipeline vs collection size (s)" source="docs/performance.md">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={sentimentPipelineScaling} margin={{ top: 8, right: 16, left: -12 }}>
              <CartesianGrid vertical={false} stroke={t.grid} />
              <XAxis dataKey="posts" stroke={t.axis} fontSize={12} />
              <YAxis stroke={t.axis} fontSize={12} unit="s" />
              <Tooltip {...Tip({ t })} formatter={(v) => `${v} s`} />
              <Line type="monotone" dataKey="seconds" name="Pipeline time" stroke={C.slate} strokeWidth={2.5} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
          <p className="note">Full-collection pipelines took about 0.2–0.9 s on 100K posts and 6.2–27.1 s on 2.94M: linear growth, which is why the dashboard reads rollups.</p>
        </Card>
      </div>

      <Card title="NLP throughput on 20,000 English posts (texts/s)" source="experiments/results/nlp_throughput.json" className="wide">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={nlpThroughput} layout="vertical" margin={{ left: 8, right: 24 }}>
            <CartesianGrid horizontal={false} stroke={t.grid} />
            <XAxis type="number" stroke={t.axis} fontSize={12} tickFormatter={(v) => `${v / 1000}K`} />
            <YAxis type="category" dataKey="model" width={200} stroke={t.axis} fontSize={12} />
            <Tooltip {...Tip({ t })} formatter={(v) => [fmt(v), 'texts/s']} />
            <Bar dataKey="rate" radius={[0, 4, 4, 0]}>
              {nlpThroughput.map((d, i) => <Cell key={d.model} fill={[C.clay, C.slate, C.olive][i]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="note">
          The end-to-end enrichment job processed 200,000 posts at 5,213 posts/s with one worker and 10,355 with two; with
          two or more workers about 16 of 19 s were spent waiting on database writes, so writes, not models, became the limit.
        </p>
      </Card>
    </Section>
  )
}

function Dashboard() {
  const [sel, setSel] = useState(0)
  const s = screens[sel]
  return (
    <Section
      id="dashboard"
      eyebrow="React dashboard"
      title="Eleven pages over the same MongoDB data"
      intro="Overview, Sentiment, Trends, Topics, Engagement, Geography & language, Anomalies, Data explorer, Performance, Ingestion and About dataset. Global filters live in the URL; every chart shows which collection answered and how long it took."
    >
      <div className="tabs" role="tablist" aria-label="Dashboard screenshots">
        {screens.map((x, i) => (
          <button key={x.file} role="tab" aria-selected={i === sel} className={i === sel ? 'tab active' : 'tab'} onClick={() => setSel(i)}>{x.title}</button>
        ))}
      </div>
      <figure className="shot">
        <img src={`${BASE}screens/${s.file}`} alt={`${s.title} page of the dashboard`} loading="lazy" />
        <figcaption>{s.caption}</figcaption>
      </figure>
    </Section>
  )
}

function Code() {
  return (
    <Section id="code" eyebrow="Source" title="Explore the code" intro="Everything is in one repository: backend, dashboard, scripts, experiments and documentation.">
      <div className="links">
        {codeLinks.map((l) => (
          <a key={l.path} href={l.dir ? tree(l.path) : blob(l.path)} className="link-card">
            <strong>{l.title}</strong>
            <span>{l.desc}</span>
            <code>{l.path}</code>
          </a>
        ))}
      </div>
      <Card title="Run it locally">
        <pre className="code">{`docker compose up -d mongo
cd backend && pip install -r requirements-dev.txt
python ../scripts/download_data.py
python ../scripts/ingest.py ../data/raw/ira538 --profile ira538 --source ira538 --workers 4
python ../scripts/train_sentiment.py && python ../scripts/train_topics.py
python ../scripts/run_nlp.py --workers 4
python ../scripts/synthesize_engagement.py
python ../scripts/build_rollups.py
uvicorn app.main:app --reload
cd ../frontend && npm install && npm run dev`}</pre>
        <p className="note">Full instructions in the <a href={blob('README.md')}>README</a>.</p>
      </Card>
    </Section>
  )
}

export default function App() {
  const dark = useDarkMode()
  const active = useActiveSection()
  const t = chartTheme(dark)
  return (
    <>
      <a href="#main" className="skip">Skip to content</a>
      <Header active={active} />
      <main id="main" className="container">
        <Hero />
        <Architecture />
        <Dataset t={t} />
        <MongoDesign />
        <Methods t={t} />
        <Results t={t} />
        <Dashboard />
        <Code />
      </main>
      <footer className="footer">
        <div className="container footer-inner">
          <p>Large-Scale Social Media Sentiment and Trend Analytics Using MongoDB · Big Data Analytics course project</p>
          <p>
            Data: FiveThirtyEight / Clemson University, CC BY 4.0. Engagement values are synthetic. Every number on this
            page comes from the project's <a href={tree('docs')}>documentation</a> and measured experiment results.
          </p>
        </div>
      </footer>
    </>
  )
}
