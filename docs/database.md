# MongoDB design

Database: `social_analytics` (configurable with `MONGO_DB`). Tested with MongoDB 8.0.23.

## Collections

| Collection | Documents (full dataset) | Purpose | Written by |
| --- | ---: | --- | --- |
| `posts` | 2,944,814 | one document per post: raw text, cleaned text, entities, user, NLP results | ingestion, NLP enrichment, synthetic engagement script |
| `daily_cube` | 130,165 | counts and sums per day x language x country x sentiment x topic | rollup pipeline |
| `hourly_cube` | 171,126 | counts per hour x language x sentiment | rollup pipeline |
| `hashtag_daily` | 417,837 | per day x hashtag: posts, reach, engagement, sentiment mix | rollup pipeline (`$unwind`) |
| `keyword_daily` | 4,423,111 | per day x language x keyword: posts, reach | rollup pipeline (`$unwind`) |
| `users` | 2,843 | per account: activity span, volume, retweet ratio, sentiment mix | rollup pipeline |
| `topics` | 28 | topic id, label, top terms per language model | `scripts/train_topics.py` |
| `ingestion_jobs` | one per run | parameters, status, counts, cleaning statistics | ingestion pipeline |
| `performance_tests` | one per experiment run | the same results as `experiments/results/*.json` | experiment runner |

Counts are from the database after the full build; `posts` takes 3.50 GB of uncompressed BSON, 1.11 GB on disk
(WiredTiger compression) and 0.98 GB of indexes.

Each extra collection exists for a measured reason: the rollups replace multi-second scans of `posts` with
sub-second reads (see [performance.md](performance.md)); `topics` keeps model metadata out of every post.

## The `posts` document

```json
{
  "post_id": "505180048811622400",
  "source": "ira538",
  "text": "The way she climbs up and down them poles #love #rap",
  "clean_text": "The way she climbs up and down them poles love rap",
  "created_at": {"$date": "2014-08-29T02:28:00Z"},
  "language": "en",
  "location": {"country": "United States", "city": null},
  "user": {"user_id": "480763276", "username": "IRIS0_O", "followers": 2693, "following": 2166,
           "updates": 5489, "account_category": "NonEnglish", "account_type": "Russian"},
  "hashtags": ["love", "rap"],
  "mentions": [],
  "url_count": 0,
  "emojis": [],
  "post_type": "retweet",
  "is_retweet": true,
  "reach": 2693,
  "engagement": {"likes": 0, "comments": 0, "shares": 0, "total": 0, "synthetic": true,
                 "generator": "scripts/synthesize_engagement.py v1"},
  "sentiment": {"label": "positive", "score": 0.8046, "confidence": 0.8904, "method": "tfidf_logreg"},
  "topic": {"id": "en-07", "label": "Love / Hate / Lost", "weight": 0.0854, "method": "tfidf_nmf"},
  "keywords": ["climbs", "love rap", "rap", "love"],
  "text_hash": "b28261dae76c854927c9e745",
  "quality_flags": [],
  "processed": true,
  "ingested_at": {"$date": "2026-10-08T06:26:38Z"},
  "ingestion_job_id": "8a3878f47872",
  "processed_at": {"$date": "2026-10-08T06:41:45Z"}
}
```

This is a real document from the database. Design choices:

* **Embedding, not references.** User fields that analytics filter on are copied into each post, so no query
  needs a join. The `users` collection is a derived summary, not the source of truth.
* **Arrays for entities.** `hashtags`, `mentions` and `keywords` are arrays, indexed as multikey and analysed
  with `$unwind`.
* **NLP results as sub-documents** with the method that produced them, so models can be swapped and compared.
* **`processed` flag** plus a partial index lets the NLP job resume where it stopped.
* **`text` and `clean_text` both kept**: the original for display and audit, the cleaned version for NLP
  and search.

## Validation

`backend/app/database/schema.py` installs a `$jsonSchema` validator with `validationLevel: strict` and
`validationAction: error`. Required: `post_id`, `text`, `clean_text`, `created_at`, `hashtags`, `mentions`,
`processed`, `source`. Typed: `created_at` must be a BSON date, counts must be non-negative integers,
`sentiment.label` must be one of the three classes. A document that bypasses the Python pipeline and breaks these
rules is rejected by the server (tested in `backend/tests/test_integration_db.py`).

## Indexes

Defined in `backend/app/database/indexes.py`, each with the reason it exists. The API endpoint
`GET /api/performance/indexes` lists them with their current sizes.

### `posts`

| Name | Keys | Options | Why |
| --- | --- | --- | --- |
| `uniq_post_id` | `post_id` | unique | one document per source post; bulk inserts rely on it to reject duplicates server-side (error 11000) |
| `created_at` | `created_at` | | date ranges and chronological sorting |
| `sentiment_created` | `sentiment.label`, `created_at` | | equality on sentiment + range on date |
| `language_created` | `language`, `created_at` | | equality on language + range on date |
| `country_created` | `location.country`, `created_at` | | geography filter + date range |
| `hashtags_created` | `hashtags`, `created_at` | multikey | posts containing a hashtag, by date |
| `topic_created` | `topic.id`, `created_at` | | topic drill-down |
| `user_created` | `user.username`, `created_at` desc | | one account's timeline, newest first |
| `text_hash` | `text_hash` | | find identical texts across accounts (copy-paste campaigns) |
| `unprocessed_partial` | `processed` | partial: `processed: false` | the NLP job finds its next batch without scanning processed posts; the index is empty when all posts are processed |
| `engagement_total` | `engagement.total` desc | sparse | top-N posts by engagement without an in-memory sort |
| `text_search` | `clean_text` (text) | `default_language: none` | keyword search; no stemming because the corpus is multilingual |

The compound indexes follow the **equality, sort, range** rule: the field tested for equality comes first and
the date (range and sort) second, so one index serves "negative posts in October 2016, newest first".

Fields such as `is_retweet` or `post_type` are deliberately **not** indexed: they have two or three values, so an
index would still return a large share of the collection and the planner would rarely choose it.

### Rollup collections

| Collection | Index | Why |
| --- | --- | --- |
| `daily_cube` | unique (`day`, `language`, `country`, `sentiment`, `topic_id`) | `$merge` upsert key; the `day` prefix serves date ranges |
| `daily_cube` | `topic_id`, `day` | topic timelines without scanning other topics |
| `hourly_cube` | unique (`hour`, `language`, `sentiment`) | `$merge` key, hour ranges |
| `hashtag_daily` | unique (`day`, `hashtag`); (`hashtag`, `day`) | trend windows; one hashtag's timeline |
| `keyword_daily` | unique (`day`, `language`, `keyword`); (`keyword`, `day`) | keyword trend windows; one keyword's timeline |
| `users` | `posts` desc | most active accounts |
| `ingestion_jobs` | `started_at` desc | latest jobs first |
| `performance_tests` | `experiment`, `run_at` desc | latest result per experiment |

### Checking that indexes are used

```js
db.posts.find({"sentiment.label": "negative",
               created_at: {$gte: ISODate("2016-10-01"), $lt: ISODate("2016-11-01")}})
        .explain("executionStats")
```

The Performance page runs representative queries through `explain("executionStats")`
(`GET /api/performance/explain/{name}`) and shows the winning plan, keys examined and documents examined.
Experiment 5 in [performance.md](performance.md) compares each one with a forced collection scan.

## Aggregation pipelines

Every statistic shown in the dashboard is computed by MongoDB. The main pipelines and the operators they
demonstrate:

| Pipeline | Operators | File |
| --- | --- | --- |
| Daily cube | `$match`, `$group` on a compound key with `$dateTrunc`, conditional sums (`$cond`), `$project`, `$merge` / `$out` | `rollups.py` |
| Hashtag and keyword rollups | `$match` on `array.0` existence, `$project`, **`$unwind`**, `$group`, `$merge` | `rollups.py` |
| Users rollup | `$group` with `$min` / `$max` / `$addToSet`, `$dateDiff`, `$round`, `$merge` | `rollups.py` |
| Overview | **`$facet`** (totals, sentiment, topics, languages, countries, date range in one pass) | `queries.py` |
| Sentiment over time | `$group` by `$dateTrunc` bucket (day / week starting Monday / month) and label | `queries.py` |
| Trends | `$match` on two date windows, `$group` with conditional sums per window, `$set` for growth and trend score (`$log10`, `$log`), `$sort`, `$limit` | `queries.py` |
| Anomaly features | **`$setWindowFields`** rolling mean and standard deviation over the 28 previous days | `anomalies.py` |
| Activity heatmap | `$isoDayOfWeek`, `$hour` on `hourly_cube` | `queries.py` |
| Top accounts by engagement (experiment) | `$group`, `$sort`, `$limit`, **`$lookup`** into `users` | `experiments/run_experiments.py` |
| Benchmark copies | `$sort`, `$limit`, `$out` into another database | `experiments/run_experiments.py` |

Example, the hashtag rollup:

```js
db.posts.aggregate([
  {$match: {"hashtags.0": {$exists: true}}},
  {$project: {hashtags: 1, created_at: 1, reach: 1, "sentiment.label": 1, "engagement.total": 1}},
  {$unwind: "$hashtags"},
  {$group: {_id: {day: {$dateTrunc: {date: "$created_at", unit: "day"}}, hashtag: "$hashtags"},
            posts: {$sum: 1}, reach: {$sum: {$ifNull: ["$reach", 0]}},
            positive: {$sum: {$cond: [{$eq: ["$sentiment.label", "positive"]}, 1, 0]}}, ...}},
  {$project: {_id: 0, day: "$_id.day", hashtag: "$_id.hashtag", posts: 1, reach: 1, ...}},
  {$merge: {into: "hashtag_daily", on: ["day", "hashtag"], whenMatched: "replace", whenNotMatched: "insert"}}
], {allowDiskUse: true})
```

`allowDiskUse` lets large `$group` stages spill to disk instead of failing at the 100 MB per-stage memory limit,
which matters on a 16 GB laptop.

## Incremental refresh

After an upload, `services/jobs.py` runs ingestion, then NLP on the new posts, then `build_all(start, end)` for
the date range the job touched. With a range, every rollup pipeline starts with `$match` on that range and ends
with `$merge`, so only the affected cube rows are replaced. The `users` rollup is recomputed in full because one
account's statistics span all dates (it is small: 2,843 rows).
