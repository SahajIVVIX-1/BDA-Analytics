# Dataset

## Main dataset: FiveThirtyEight "russian-troll-tweets"

| Property | Value |
| --- | --- |
| Source | https://github.com/fivethirtyeight/russian-troll-tweets (13 CSV files, `IRAhandle_tweets_1.csv` to `_13.csv`) |
| Collected by | Darren Linvill and Patrick Warren (Clemson University), published by FiveThirtyEight in 2018 |
| Licence | Creative Commons Attribution 4.0 (CC BY 4.0), as stated by FiveThirtyEight's data repository |
| What it is | Tweets from accounts that Twitter identified as connected to the Internet Research Agency (IRA) |
| Rows read by this project | 2,946,207 |
| Stored in MongoDB | 2,944,814 (1,392 duplicate `tweet_id`s and 1 empty tweet removed) |
| Accounts | 2,843 distinct author handles |
| Date range | 2012-02-02 to 2018-05-30 (UTC assumed, see below) |
| Download size | about 1 GB of CSV |

All counts in this table come from the ingestion job record in the `ingestion_jobs` collection and from the
database itself; they are reproduced by `python scripts/ingest.py data/raw/ira538`.

### Fields and how they are used

| Source column | Stored as | Notes |
| --- | --- | --- |
| `tweet_id` | `post_id` | unique index; duplicates rejected |
| `content` | `text`, `clean_text` | cleaned text drives NLP and search |
| `publish_date` | `created_at` | format `M/D/YYYY H:MM`; no time zone in the source, **assumed UTC** |
| `language` | `language` | language names mapped to ISO 639-1 codes (`English` -> `en`) |
| `region` | `location.country` | account-level region assigned by the original researchers' tooling; country only, no city; `Unknown` -> null |
| `author` | `user.username` | |
| `alt_external_id` | `user.user_id` | `external_author_id` lost precision in the CSV, so the alternative id is used |
| `followers`, `following`, `updates` | `user.*` | follower count also stored as `reach` |
| `account_category`, `account_type` | `user.*` | researcher-coded themes (RightTroll, LeftTroll, NewsFeed, ...) |
| `post_type`, `retweet` | `post_type`, `is_retweet` | |
| (none) | `hashtags`, `mentions`, `url_count`, `emojis` | extracted from the text during cleaning |

### Evaluation against the brief

| Criterion | Available? |
| --- | --- |
| Number of records | Yes: 2.95M real tweets |
| Timestamp | Yes, minute precision, time zone not stated (UTC assumed) |
| Text | Yes |
| Sentiment labels | **No.** Sentiment is predicted by a model trained on TweetEval |
| Hashtags | Not as a column; extracted from text (1,129,917 posts have at least one) |
| Engagement (likes / replies / shares) | **No.** Generated synthetically and flagged, see below |
| Language | Yes (56 language values after normalisation; 8,320 posts with none) |
| Location | Account-level country for 80.6% of posts; 570,812 posts unknown |
| Licence | CC BY 4.0 |

### Data quality findings (from the ingestion run)

* 1,386 rows repeat a `tweet_id` already seen in the same batch and 6 repeat one from an earlier batch.
* 1 row has an empty `content` field.
* 32,125 posts have no text left after removing URLs, mentions and emoji (`no_text_content` flag).
* 123,874 posts are links with fewer than four words (`link_only`); 104,415 mention five or more accounts
  (`mention_stuffing`); 39,176 use five or more hashtags (`hashtag_stuffing`).
* 44% of posts are retweets.
* Volume is very uneven: 488 posts in 2012, 199 in 2013, 7,722 in 2014, then 821,443 (2015), 1,122,936 (2016)
  and 984,720 (2017), so 99.5% of posts fall in 2015-2017; only 7,306 are from 2018. The busiest day has 18,634
  posts (2016-10-06). There is a collection gap from about 2017-10-23 to 2017-11-06 with only 20 to 50 posts per day, and a
  sparse tail into 2018. The dashboard treats 2017-11-13 (the 99th percentile of post dates) as the end of the
  main activity period for "latest window" defaults.

Flagged posts are kept, because spam-like behaviour is part of what the dataset documents; the flags can be
used to filter them.

### Representativeness

The accounts are a coordinated influence operation, not a sample of Twitter users. Results describe what those
accounts posted. They cannot be read as public opinion, and nothing in this project measures how real users
reacted to them.

## Sentiment training data: TweetEval

| Property | Value |
| --- | --- |
| Source | https://github.com/cardiffnlp/tweeteval, `datasets/sentiment` |
| Task | 3 classes: negative, neutral, positive (originally SemEval-2017 Task 4A) |
| Splits used | official train 45,615 / validation 2,000 / test 12,284 |
| Use | training and evaluating the sentiment model only; never stored in MongoDB |

The TweetEval README says it is "released without any restrictions but restrictions may apply to individual
tasks (which are derived from existing datasets) or Twitter". The project downloads it at build time and does not
commit it.

## Synthetic data

The only synthetic values in the project are the engagement counts (`likes`, `comments`, `shares`, `total`).
They are produced by `scripts/synthesize_engagement.py` from the author's real follower count, whether the post
is a retweet, and a seed derived from the post id. They do **not** depend on sentiment, topic, hashtags or time,
so any difference in engagement between topics or sentiments only reflects follower counts. Every value carries
`engagement.synthetic: true`; the API returns `synthetic: true` with engagement figures and the dashboard shows
a *Synthetic data* badge. `python scripts/synthesize_engagement.py --remove` deletes them again.

Datasets uploaded through the dashboard that contain real engagement columns (`likes`, `replies`, `retweets`,
...) are stored with `synthetic: false` and are never overwritten.

## Getting the data

```bash
python scripts/download_data.py             # both datasets into data/raw/
```

`data/raw/` is git-ignored; the repository contains code only.

## Alternatives considered

* **Sentiment140** (1.6M tweets with distant-supervision labels): rejected because the publicly mirrored copy
  available during the build lacked usable timestamps, which trend and time analysis need.
* Twitter / X API: no free bulk access; data could not be redistributed.
