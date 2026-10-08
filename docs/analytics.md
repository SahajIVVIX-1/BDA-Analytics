# Analytics

What the platform computes, where it is computed, and which page shows it. Methods and their assumptions are in
[methodology.md](methodology.md).

## Shared filters

Every analytics endpoint accepts the same filters (`backend/app/analytics/source.py`):

| Filter | Meaning | Served from the cube? |
| --- | --- | --- |
| `start`, `end` | inclusive dates (YYYY-MM-DD) | yes |
| `language` | ISO code (`en`, `ru`, ...) | yes |
| `country` | account region | yes |
| `sentiment` | `positive`, `neutral`, `negative`, `not_analyzed` | yes |
| `topic` | topic id (`en-03`) | yes |
| `hashtag` | one hashtag (with or without `#`) | no, live on `posts` |
| `q` | full-text search terms | no |
| `min_engagement` | minimum `engagement.total` | no |
| `exclude_retweets` | drop retweets | no |
| `user` | one account | no |
| `mode` | `auto` (default), `cube`, `live` | |

In `auto` mode a request whose filters are all cube dimensions reads `daily_cube`; anything else runs the same
aggregation on `posts`. Every response includes `meta.source` (`daily_cube` or `posts`) and `meta.query_ms`, and
the dashboard shows both as a badge on each chart.

## Modules

### Overview (`/api/dashboard/overview`, page *Overview*)

One `$facet` pass returns: total posts, sentiment counts and percentages (of analysed English posts), average
sentiment score, total reach, retweet share, synthetic engagement totals, topic / language / country counts,
date range, account count, and the number of growing hashtags in the last 7 days of the main activity period.

### Sentiment (`/api/analytics/sentiment`, page *Sentiment*)

Distribution, share positive / negative per day, week or month (periods with fewer than 100 analysed posts are
returned as null to avoid 0%/100% swings), and breakdowns by topic, language and country with
`net sentiment = (positive - negative) / analysed`.

### Topics (`/api/analytics/topics`, page *Topics*)

Posts per topic, share, sentiment mix, net sentiment, average (synthetic) engagement, reach, a timeline of the
eight largest topics, and 30-day growth and share growth from the trend module.

### Trends (`/api/analytics/trends`, `/api/analytics/hashtags`, page *Trends*)

Window-over-window ranking of hashtags (from `hashtag_daily`), keywords (`keyword_daily`, per language) or
topics (`daily_cube`) with current and previous counts, growth %, share growth %, trend score, average reach and a
daily timeline of the top items over the eight preceding windows. Any end date can be chosen, so past events can
be replayed (the page offers presets such as 2016-11-08, US election day).

### Engagement (`/api/analytics/engagement`, page *Engagement*)

Totals of likes, comments, shares, engagement per 1,000 followers, average engagement over time, by sentiment,
by topic, and top posts (read through the `engagement.total` index). Every response carries `synthetic: true`
for this dataset and the page explains why.

### Time patterns and anomalies (`/api/analytics/timeseries`, `/activity`, `/anomalies`, page *Anomalies*)

Posts, reach and engagement per hour, day, week or month (optionally split by sentiment, topic, language or country);
a weekday x hour heatmap (UTC) from `hourly_cube`; anomalous days from rolling z-scores, IQR and Isolation Forest
with the reasons each day was flagged.

### Geography and language (`/api/analytics/geography`, `/languages`, `/users`, page *Geography & language*)

Posts, sentiment and top topics per country (account-level region, 80.6% known) and per language; account
categories from the researchers' coding (RightTroll, LeftTroll, NewsFeed, HashtagGamer, ...) with accounts, posts,
retweet ratio, posts per active day and net sentiment.

### Data Explorer (`/api/posts`, `/api/search`, `/api/posts/{id}`, page *Data explorer*)

Paginated posts with every filter, sorting by date, engagement or text relevance (`$text` score). Opening a post
shows the full stored document, including NLP outputs and how many other posts have identical text
(`text_hash`). Counts are capped at 100,000 for filtered queries to keep them fast; unfiltered totals use the
collection's estimated count.

### Performance (`/api/performance*`, page *Performance*)

Measured experiment results (from `experiments/results/` and the `performance_tests` collection), live index
list with sizes, collection statistics and on-demand `explain()` of representative queries.

### Ingestion (`/api/ingestion/*`, page *Ingestion*)

Upload a CSV / JSON / JSONL file, preview its columns, start a job (ingest, NLP, incremental rollup refresh) and
follow its statistics.

## Some findings from the data

These come from the dashboard on the full dataset and are descriptive only.

* 71.8% of posts are English and 20.7% Russian.
* Of the English posts analysed by the model, 16.8% are predicted positive, 52.0% neutral and 31.2% negative
  (model predictions, not ground truth; see the model's measured accuracy in [performance.md](performance.md)).
* Activity is concentrated in 2015-2017; the busiest single day in the data is 2016-10-06 with 18,634 posts,
  which the anomaly page flags as a volume spike (z = 7.1 against the previous 28 days).
* In the 7 days to 2016-11-08 (US election day), the fastest-growing hashtags include `#trumpforpresident`,
  `#2016electionin3words`, `#electionday` and `#hillaryforprison2016`.
* Account categories behave differently: NewsFeed accounts post about 20 times per active day with a 10% retweet
  ratio, while NonEnglish and HashtagGamer accounts retweet much more (71% and 66%).
