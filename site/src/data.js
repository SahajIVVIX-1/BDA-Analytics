// Every number on this site is copied from docs/report.md, docs/database.md,
// docs/methodology.md or docs/performance.md. Nothing here is estimated.

export const REPO = 'https://github.com/SahajIVVIX-1/BDA-Analytics'
export const blob = (path) => `${REPO}/blob/main/${path}`
export const tree = (path) => `${REPO}/tree/main/${path}`

export const headline = [
  { value: '2,944,814', label: 'real tweets stored in MongoDB' },
  { value: '12', label: 'purpose-built indexes on posts' },
  { value: '5', label: 'rollup collections from aggregation pipelines' },
  { value: '26', label: 'FastAPI endpoints' },
  { value: '10', label: 'dashboard pages' },
  { value: '35–44×', label: 'faster dashboard queries from rollups' },
]

export const ingestionStats = [
  ['Records read', '2,946,207'],
  ['Inserted', '2,944,814'],
  ['Duplicates (same tweet_id)', '1,392'],
  ['Invalid (empty text)', '1'],
  ['Hashtags extracted', '1,753,395'],
  ['Mentions extracted', '1,153,675'],
  ['URLs removed', '2,827,842'],
  ['Emoji removed', '93,108'],
  ['Posts without language', '8,320'],
  ['Posts without location', '570,812'],
  ['Time (4 workers, batch 5,000)', '316.3 s · 9,314 records/s'],
]

export const qualityFlags = [
  { flag: 'Link only', count: 123874 },
  { flag: 'Mention stuffing', count: 104415 },
  { flag: 'Short', count: 96748 },
  { flag: 'Hashtag stuffing', count: 39176 },
  { flag: 'No text left', count: 32125 },
  { flag: 'Repetitive', count: 1068 },
]

export const collections = [
  { name: 'posts', docs: '2,944,814', purpose: 'One document per post: raw and cleaned text, entities, embedded user, NLP results' },
  { name: 'daily_cube', docs: '130,165', purpose: 'Counts and sums per day × language × country × sentiment × topic' },
  { name: 'hourly_cube', docs: '171,126', purpose: 'Counts per hour × language × sentiment' },
  { name: 'hashtag_daily', docs: '417,837', purpose: 'Per day × hashtag: posts, reach, engagement, sentiment mix ($unwind)' },
  { name: 'keyword_daily', docs: '4,423,111', purpose: 'Per day × language × keyword: posts, reach ($unwind)' },
  { name: 'users', docs: '2,843', purpose: 'Per account: activity span, volume, retweet ratio, sentiment mix' },
  { name: 'topics', docs: '28', purpose: 'Topic id, label and top terms per language model' },
  { name: 'ingestion_jobs', docs: 'one per run', purpose: 'Parameters, status, counts, cleaning statistics' },
  { name: 'performance_tests', docs: 'one per run', purpose: 'Same results as experiments/results/*.json' },
]

export const indexes = [
  ['uniq_post_id', 'post_id', 'unique', 'One document per source post; bulk inserts reject duplicates server-side (error 11000)'],
  ['created_at', 'created_at', '', 'Date ranges and chronological sorting'],
  ['sentiment_created', 'sentiment.label, created_at', '', 'Equality on sentiment + range on date'],
  ['language_created', 'language, created_at', '', 'Equality on language + range on date'],
  ['country_created', 'location.country, created_at', '', 'Geography filter + date range'],
  ['hashtags_created', 'hashtags, created_at', 'multikey', 'Posts containing a hashtag, by date'],
  ['topic_created', 'topic.id, created_at', '', 'Topic drill-down'],
  ['user_created', 'user.username, created_at desc', '', "One account's timeline, newest first"],
  ['text_hash', 'text_hash', '', 'Find identical texts across accounts (copy-paste campaigns)'],
  ['unprocessed_partial', 'processed', 'partial: processed=false', 'NLP job finds its next batch without scanning processed posts'],
  ['engagement_total', 'engagement.total desc', 'sparse', 'Top-N posts by engagement without an in-memory sort'],
  ['text_search', 'clean_text (text)', 'default_language: none', 'Keyword search; no stemming because the corpus is multilingual'],
]

export const aggregationOps = ['$match', '$group', '$project', '$sort', '$limit', '$unwind', '$lookup', '$facet', '$setWindowFields', '$dateTrunc', '$merge', '$out']

export const sentimentModels = [
  { model: 'VADER', f1: 0.526, acc: 0.528, recall: 0.564, valF1: 0.56 },
  { model: 'TF-IDF + Naive Bayes', f1: 0.455, acc: 0.539, recall: 0.502, valF1: 0.506 },
  { model: 'TF-IDF + Logistic regression', f1: 0.582, acc: 0.586, recall: 0.593, valF1: 0.65 },
]

export const sentimentMix = [
  { label: 'Positive', share: 16.8 },
  { label: 'Neutral', share: 52.0 },
  { label: 'Negative', share: 31.2 },
]

export const ingestionScaling = [
  { posts: '100K', n: 100000, load: 9.1, rate: 10992, index: 9.5 },
  { posts: '500K', n: 500000, load: 42.3, rate: 11815, index: 46.9 },
  { posts: '1M', n: 1000000, load: 91.0, rate: 10992, index: 99.1 },
  { posts: '2.94M', n: 2944814, load: 297.1, rate: 9917, index: 310.9 },
]

export const workers = [
  { workers: '1 worker', rate: 6963 },
  { workers: '2 workers', rate: 13284 },
  { workers: '4 workers', rate: 11526 },
]

export const indexVsScan = [
  { query: 'Negative posts in Oct 2016', scan: 4955, indexed: 201, examined: '33,703' },
  { query: 'Posts with one hashtag', scan: 3454, indexed: 64, examined: '16,172' },
  { query: 'One language in a date range', scan: 3412, indexed: 122, examined: '28,734' },
  { query: 'One country in a date range', scan: 3181, indexed: 72, examined: '27,178' },
  { query: 'Posts of one day', scan: 3394, indexed: 22, examined: '7,365' },
  { query: 'Latest 50 posts of one account', scan: 3256, indexed: 1, indexedLabel: '< 1', examined: '50' },
]

export const sentimentPipelineScaling = [
  { posts: '100K', seconds: 0.77 },
  { posts: '500K', seconds: 3.19 },
  { posts: '1M', seconds: 7.22 },
  { posts: '2.94M', seconds: 21.26 },
]

export const rollupVsLive = [
  { query: 'Overview KPIs', live: 33.7, rollup: 0.96, speedup: '35×' },
  { query: 'Sentiment page', live: 31.5, rollup: 0.87, speedup: '36×' },
  { query: 'Topics page', live: 36.7, rollup: 0.83, speedup: '44×' },
  { query: 'Geography page', live: 25.6, rollup: 0.69, speedup: '37×' },
  { query: 'Overview, English 2016', live: 14.4, rollup: 0.42, speedup: '34×' },
]

export const nlpThroughput = [
  { model: 'Logistic regression sentiment', rate: 24067 },
  { model: 'VADER', rate: 17767 },
  { model: 'NMF topics + keywords', rate: 25677 },
]

export const trendExample = [
  '#trumpforpresident',
  '#sometimesitsokto',
  '#2016electionin3words',
  '#electionday',
  '#hillaryforprison2016',
]

export const screens = [
  { file: 'overview.png', title: 'Overview', caption: 'KPIs, volume over time and sentiment mix, answered from the daily cube.' },
  { file: 'sentiment.png', title: 'Sentiment', caption: 'Sentiment over time and by language for English posts.' },
  { file: 'trends.png', title: 'Trends', caption: 'Window-over-window hashtag, keyword and topic growth with the trend score.' },
  { file: 'topics.png', title: 'Topics', caption: 'NMF topics with share, timeline and sentiment mix.' },
  { file: 'anomalies.png', title: 'Anomalies', caption: 'Rolling z-score, IQR and Isolation Forest on the daily series.' },
  { file: 'explorer.png', title: 'Data explorer', caption: 'Paginated, filterable posts with full-text search.' },
  { file: 'performance.png', title: 'Performance', caption: 'Measured experiments and live explain() plans.' },
  { file: 'overview-dark.png', title: 'Dark mode', caption: 'Every page supports light and dark themes.' },
]

export const codeLinks = [
  { title: 'Ingestion pipeline', path: 'backend/app/ingestion', desc: 'Streaming readers, cleaning, normalisation, batch bulk insert', dir: true },
  { title: 'Schema & indexes', path: 'backend/app/database', desc: '$jsonSchema validator and index definitions with reasons', dir: true },
  { title: 'Rollup pipelines', path: 'backend/app/analytics/rollups.py', desc: 'daily/hourly cubes, hashtag, keyword and users rollups' },
  { title: 'Anomaly detection', path: 'backend/app/analytics/anomalies.py', desc: '$setWindowFields z-score, IQR, Isolation Forest' },
  { title: 'NLP', path: 'backend/app/nlp', desc: 'Sentiment, topics and the enrichment job', dir: true },
  { title: 'FastAPI routers', path: 'backend/app/api', desc: '26 endpoints: analytics, posts, ingestion, performance', dir: true },
  { title: 'React dashboard', path: 'frontend/src', desc: 'React 19, Vite, Tailwind, Recharts', dir: true },
  { title: 'Experiments', path: 'experiments', desc: 'run_experiments.py, make_report.py, measured JSON', dir: true },
  { title: 'Performance report', path: 'docs/performance.md', desc: 'All tables generated from measured results' },
  { title: 'Full project report', path: 'docs/report.md', desc: 'The 25-section course report' },
  { title: 'Methodology', path: 'docs/methodology.md', desc: 'Cleaning, NLP, trends, anomalies, synthetic engagement' },
  { title: 'Dataset notes', path: 'docs/dataset.md', desc: 'Source, licence, fields, gaps and representativeness' },
]
