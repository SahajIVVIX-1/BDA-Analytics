# API reference

FastAPI, base URL `http://127.0.0.1:8000`. Interactive documentation generated from the code is at `/docs`
(Swagger UI) and `/redoc`; the OpenAPI schema is at `/openapi.json`.

* All responses are JSON. Dates are ISO 8601 in UTC (`2016-11-08T00:00:00+00:00`).
* Analytics responses carry `meta: {source, query_ms}` saying which collection answered and how long it took.
* Analytics responses are cached in the API process for 120 seconds.
* Errors: `422` invalid parameters (FastAPI validation detail), `404` unknown post or job, `413` upload too large,
  `415` unsupported file type, `503` MongoDB unreachable, `500` other database errors. Error bodies never include
  connection strings.

## Common filter parameters

Accepted by every endpoint marked **[filters]**. See [analytics.md](analytics.md#shared-filters).

`start`, `end` (YYYY-MM-DD, inclusive), `language`, `country`, `sentiment` (`positive|neutral|negative|not_analyzed`),
`topic`, `hashtag`, `q`, `min_engagement` (int >= 0), `exclude_retweets` (bool), `user`, `mode`
(`auto|cube|live`).

## Endpoints

### Health and metadata

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | MongoDB reachability, database name, post and processed-post counts, API and server versions |
| GET | `/api/meta/filters` | values for filter dropdowns (languages, countries, topics with counts) and the date range |

```json
GET /api/health
{"status": "ok", "mongodb": true, "database": "social_analytics", "posts": 2944814,
 "processed_posts": 2944814, "version": "1.0.0", "server_version": "8.0.23"}
```

### Dashboard and analytics

| Method | Path | Extra parameters | Description |
| --- | --- | --- | --- |
| GET | `/api/dashboard/overview` [filters] | | KPI values for the overview page |
| GET | `/api/analytics/timeseries` [filters] | `granularity` (`hour\|day\|week\|month`), `split_by` (`sentiment\|topic\|language\|country`) | posts, reach, engagement per time bucket |
| GET | `/api/analytics/activity` [filters] | | weekday x hour heatmap (UTC) |
| GET | `/api/analytics/sentiment` [filters] | `granularity` | distribution, over time, by topic / language / country |
| GET | `/api/analytics/topics` [filters] | `granularity`, `top` | distribution, timeline, sentiment, engagement, growth |
| GET | `/api/analytics/trends` | `kind` (`hashtag\|keyword\|topic`), `end`, `window_days`, `limit`, `min_count`, `language`, `timeline` | window-over-window trend ranking |
| GET | `/api/analytics/hashtags` [filters] | `limit` | most used hashtags |
| GET | `/api/analytics/engagement` [filters] | `granularity`, `top` | totals, over time, by sentiment / topic, top posts |
| GET | `/api/analytics/geography` [filters] | | per country |
| GET | `/api/analytics/languages` [filters] | | per language |
| GET | `/api/analytics/anomalies` [filters] | `z` (1-10, default 3), `contamination` (0-0.2, default 0.02), `min_volume` (default 100) | anomalous days and the daily series |
| GET | `/api/analytics/users` | `limit`, `category` | most active accounts and account categories |

Example:

```
GET /api/analytics/trends?kind=hashtag&end=2016-11-08&window_days=7&limit=1&timeline=false
```

```json
{
  "kind": "hashtag",
  "window_days": 7,
  "window": {"current": ["2016-11-02T00:00:00+00:00", "2016-11-09T00:00:00+00:00"],
             "previous": ["2016-10-26T00:00:00+00:00", "2016-11-02T00:00:00+00:00"]},
  "totals": {"current": 27856, "previous": 26647},
  "warning": null,
  "items": [{"key": "trumpforpresident", "label": "trumpforpresident", "current": 1682, "previous": 1,
             "growth_pct": 168100.0, "share_growth_pct": 160799.8, "avg_reach": 1877, "trend_score": 34.837}],
  "formula": "log10(1+current) * log2((current+5)/(previous+5)) * (1+0.1*log10(1+avg_reach))",
  "meta": {"source": "hashtag_daily", "query_ms": 189.8}
}
```

(Real response from the full dataset.)

### Posts and search

| Method | Path | Parameters | Description |
| --- | --- | --- | --- |
| GET | `/api/posts` [filters] | `page` (1-400), `page_size` (1-100, default 25), `sort` (`newest\|oldest\|engagement\|relevance`) | filtered, paginated posts |
| GET | `/api/search` [filters] | `q` (required), `page`, `page_size`, `sort` (`relevance\|newest\|engagement`) | full-text search with the MongoDB text index |
| GET | `/api/posts/{post_id}` | MongoDB `_id` or source `post_id` | one post with all stored fields and the number of posts with identical text |

Page response: `{items: [...], page, page_size, total, total_capped, meta}`. `total` is exact up to 100,000 for
filtered queries (`total_capped: true` above that).

### Ingestion

| Method | Path | Body / parameters | Description |
| --- | --- | --- | --- |
| POST | `/api/ingestion/upload` | multipart `file` (`.csv`, `.json`, `.jsonl`, optionally `.gz`; up to `MAX_UPLOAD_MB`, default 500) | stores the file under `data/uploads/`, returns `upload_id`, detected format and preview columns. `201`, or `413` / `415` / `422` |
| POST | `/api/ingestion/start` | JSON `{upload_id or path, profile: generic\|ira538, source, batch_size: 100-50000, limit, run_nlp, refresh_rollups}` | starts a background job: ingest, then NLP, then incremental rollups. `path` must be inside `data/` |
| GET | `/api/ingestion/jobs` | `limit` | recent jobs |
| GET | `/api/ingestion/jobs/{job_id}` | | one job with status and statistics |
| GET | `/api/ingestion/preview` | `path`, `n` | first records of a data file |

The `generic` profile accepts common column names: `id` / `post_id` / `tweet_id`, `text` / `content` /
`full_text`, `created_at` / `timestamp` / `date`, `lang` / `language`, `country` / `region`, `username` /
`screen_name` / `author`, `followers` / `followers_count`, `likes` / `favorite_count`, `replies` / `reply_count`,
`retweets` / `retweet_count` / `shares`, and nested JSON such as `user.screen_name`.

Example:

```bash
curl -F "file=@my_posts.csv" http://127.0.0.1:8000/api/ingestion/upload
curl -X POST http://127.0.0.1:8000/api/ingestion/start -H "Content-Type: application/json" \
     -d '{"upload_id": "<id from upload>", "profile": "generic", "source": "my-upload"}'
curl http://127.0.0.1:8000/api/ingestion/jobs
```

### Performance

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/performance` | all experiment results (JSON files and the `performance_tests` collection) |
| GET | `/api/performance/indexes` | indexes per collection, the reason each exists, sizes |
| GET | `/api/performance/collections` | document counts and storage sizes |
| GET | `/api/performance/explain/{name}` | `explain("executionStats")` for `sentiment_range`, `hashtag_lookup`, `language_range`, `user_timeline` or `text_search` |
