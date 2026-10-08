# Presentation structure

About 15 slides for a 15-20 minute talk plus a live demo. Each slide lists what to show and the one point to
make. Screenshots come from the running dashboard; numbers from [performance.md](performance.md).

| # | Slide | Show | Point to make |
| --- | --- | --- | --- |
| 1 | Title | project title, names, course | |
| 2 | Problem | a few example tweets from the Explorer; the volume per day chart | millions of short, noisy, multilingual posts cannot be read by hand; we need storage, processing and analytics that scale |
| 3 | Objectives | 5 bullets: ingest at scale, store in MongoDB, analyse (sentiment, topics, trends, anomalies), serve via API + dashboard, measure performance | |
| 4 | Dataset | table from [dataset.md](dataset.md): 2.95M real IRA tweets, fields, licence; what is missing | be upfront: troll accounts not public opinion; engagement synthetic and labelled |
| 5 | Architecture | the diagram from [architecture.md](architecture.md) | batch pipeline on one machine, MongoDB at the centre, no Spark |
| 6 | MongoDB design | the `posts` document, validator, index table | document model fits nested posts; every index answers a real query |
| 7 | Ingestion and cleaning | pipeline steps, cleaning statistics from the ingestion job | streaming + batches + bulk insert, duplicates rejected by the unique index |
| 8 | Aggregation pipelines | the hashtag rollup pipeline; list of operators used | computation happens in MongoDB; rollups make the dashboard fast |
| 9 | NLP | sentiment model comparison table (VADER, NB, LogReg); topic list | lightweight CPU models; honest accuracy and its limits |
| 10 | Trends and anomalies | Trends page at 2016-11-08; Anomalies chart | trend score formula; three anomaly methods |
| 11 | Dashboard demo | live: Overview, filter to Russian, Trends replay, Explorer search, a post's full document, Performance explain | |
| 12 | Experiment set-up | hardware line, sizes, what was measured, how (median of runs, explain) | |
| 13 | Results: ingestion and indexes | tables/charts from performance.md sections 1-5 | linear ingestion; deferred indexes; index vs collection scan |
| 14 | Results: aggregation and NLP | sections 6-7: rollup vs live speed-up, NLP throughput | pre-aggregation is the biggest win for dashboards |
| 15 | Limitations and future work | list from [report.md](report.md) sections 22-23 | single machine, no streaming, synthetic engagement, model accuracy |
| 16 | Conclusion | 3 take-aways | |

## Demo script (5 minutes)

1. Overview: point at total posts and the *pre-aggregated cube* badge with its query time.
2. Set language to Russian: KPIs and charts change; badge still says cube.
3. Add hashtag `news` in the Explorer: badge switches to `posts` (live query), explain why.
4. Trends: jump to *US election day 2016*; show growth, share growth, trend score.
5. Anomalies: hover the largest spike; show the flagged days table.
6. Open a post: show the full MongoDB document with sentiment, topic, keywords, synthetic flag.
7. Performance: run *explain* for `hashtag_lookup`; show IXSCAN, keys examined vs documents.

Keep the API running with data already loaded; the first request after start-up fills the cache, so open each
page once before presenting.
