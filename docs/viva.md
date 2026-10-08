# Viva preparation

Short answers you can say out loud, each followed by the evidence in this project. Numbers marked *(measured)*
come from [performance.md](performance.md) or the database; re-check them if you re-run the experiments on your
own laptop.

## Why MongoDB?

A social media post is a nested document: text, an author object, a location object, arrays of hashtags,
mentions and keywords, and NLP results that are added later. MongoDB stores that shape directly, indexes inside
arrays (multikey indexes on `hashtags`), validates it with `$jsonSchema`, and computes analytics where the data
lives with aggregation pipelines. New sources with extra fields (an upload with real like counts) need no schema
migration.

*Evidence:* the `posts` document in [database.md](database.md); the `hashtags_created` multikey index; rollups built
entirely by `$group`, `$unwind`, `$merge` and `$out`.

## Why is this Big Data?

By the usual "V" characteristics, and honestly scaled:

* **Volume:** 2.94M posts, 3.5 GB of BSON before compression, 4.4M rows in the keyword rollup *(measured)*.
  It is large for a laptop, not large by industry standards.
* **Variety:** semi-structured text in 56 language values, nested user metadata, arrays of entities, emoji,
  multiple input formats (CSV, JSON, JSONL, gzip).
* **Velocity:** **simulated only.** Data arrives in batches through ingestion jobs; there is no real-time stream.
* **Veracity:** duplicates (1,392 removed), an empty post, missing languages and locations, spam-like posts
  flagged, a collection gap in late 2017, and synthetic engagement that must be labelled.
* **Value:** trends, anomalies and sentiment shifts that are not visible by reading individual tweets.

The techniques are the Big Data ones that apply on one machine: streaming and batching instead of loading
everything into RAM, server-side aggregation, pre-aggregation, indexing, parallel processing, and measuring how
cost grows with data size.

## Why NoSQL?

Because the workload is read-heavy analytics over flexible, nested, append-mostly documents, with no
multi-row transactions. A document store avoids joins for the common queries, and arrays (hashtags) are
first-class instead of needing a separate table.

## Why MongoDB instead of SQL?

A relational database could store this data too. The trade-offs that decided it here:

| Need | MongoDB | Relational |
| --- | --- | --- |
| Hashtags, mentions, keywords | arrays in the document, multikey index, `$unwind` | separate junction tables and joins |
| Different upload formats | flexible fields, validation only on what analytics needs | schema migration per new field |
| NLP results added later | `$set` a sub-document | new columns or tables |
| Aggregation | `$group`, `$facet`, `$setWindowFields`, `$merge` in one pipeline | equivalent SQL (GROUP BY, window functions, materialised views) |

What SQL would do better: ad-hoc joins between large tables, strict constraints across entities, and SQL is more
widely known. For this workload neither choice is wrong; MongoDB fits the document shape and was required by the
brief.

## What are aggregation pipelines?

A sequence of stages that MongoDB runs on the server, each transforming a stream of documents: `$match` filters,
`$group` aggregates, `$project` reshapes, `$unwind` turns an array into one document per element, `$sort`,
`$limit`, `$lookup` joins another collection, `$facet` runs several sub-pipelines on the same input,
`$setWindowFields` computes rolling statistics, `$merge` / `$out` write the result to a collection. Only the
result travels to Python.

*Example in the project:* the hashtag rollup: `$match` posts with hashtags, `$project` the needed fields,
`$unwind` the hashtags array, `$group` by day and hashtag, `$merge` into `hashtag_daily`.

## Why indexes?

Without an index MongoDB must read every document (a collection scan), so query cost grows with the collection.
With an index it reads only the matching keys, so cost follows the size of the answer.

*Evidence:* experiment 5 compares each query against a forced collection scan with `explain("executionStats")`:
documents examined drop from the whole collection to roughly the number returned *(measured, see
performance.md section 5)*. Indexes are not free: experiment 4 shows that loading with all indexes in place is
slower than building them afterwards *(measured)*, and they take 0.98 GB for `posts` *(measured)*.

How the indexes were chosen: one per real query pattern, compound indexes ordered equality, sort, range (for
example `sentiment.label` then `created_at`), no indexes on two-valued fields such as `is_retweet`.

## How does sentiment analysis work?

Text is cleaned, lower-cased and turned into TF-IDF features of words and word pairs. A logistic regression
model trained on 45,615 labelled tweets from TweetEval gives the probability of negative, neutral and positive;
the highest probability is the label and P(positive) - P(negative) is the score. It was chosen over VADER (a
lexicon) and Naive Bayes by validation macro-F1.

Honest limits: test macro-F1 0.58 and macro recall 0.59 on TweetEval *(measured)*, below published baselines
(SVM 62.9 macro recall) and transformers (about 73); accuracy on the IRA tweets is not measured because they
have no labels; English only; no sarcasm handling.

## How are trends detected?

For each hashtag, keyword or topic, compare its count in the latest window (for example 7 days) with the window
before. Growth % alone exaggerates tiny counts, so the trend score is
`log10(1 + now) x log2((now + 5) / (before + 5)) x (1 + 0.1 x log10(1 + reach))`: it rewards both volume and
growth, smooths small counts, and gives a small bonus for reach. If total data volume changes a lot between the
windows, the system warns and uses share growth instead. All of this is one aggregation over the daily rollups.

*Example:* in the 7 days to 2016-11-08, `#trumpforpresident` went from 1 to 1,682 posts, trend score 34.8.

## How does the system scale?

*What it does now (implemented and measured):* streams files with constant memory; cleans in parallel worker
processes; bulk inserts in batches; builds indexes after loading; computes everything in MongoDB; pre-aggregates
into rollups so dashboard queries read about 130K rows instead of 2.9M; refreshes rollups only for the days an
upload touches. Experiments measure how time grows from 100K to 2.95M posts.

*What it would need beyond one machine (not implemented):* sharding `posts` across several MongoDB servers,
a replica set, a job queue for ingestion, and a shared cache. The pipelines themselves would run unchanged on a
sharded cluster.

## What are the limitations?

* Single machine; no distributed processing, no streaming.
* The dataset is a troll-account archive, not representative of Twitter users.
* Engagement is synthetic.
* Sentiment is English-only, modest accuracy, not validated on this dataset.
* Two thirds of English posts get no topic (weight below threshold); topic count `k` chosen by inspection.
* Timestamps assumed UTC.
* 5M-document experiment not run (dataset has 2.95M posts).
* Experiments ran on one cloud VM; laptop numbers will differ.

## What did the performance experiments demonstrate?

From the measured tables in [performance.md](performance.md) (one 4-vCPU cloud VM; re-run on your laptop):

1. Ingestion throughput stayed between about 9,900 and 11,800 records/s from 100K to 2.95M posts, so ingestion
   time grows roughly linearly: 297 s to load all 2.95M posts plus 311 s for indexes (section 1).
2. Batch size and worker count matter: batches of 100 are clearly slower than 500+, and two cleaning workers beat
   four on a 4-vCPU machine, most likely because the workers, the inserter and MongoDB compete for the same CPUs (sections 2-3).
3. Building secondary indexes after the bulk load was 16% faster in total than maintaining them during the load
   (57.3 s vs 68.1 s for 300K posts, section 4).
4. On 2.94M posts a collection scan examined every document and took 3.2-5.0 s; the indexed versions examined
   only the matching documents and took under 1 ms to 201 ms (section 5).
5. Answering dashboard queries from pre-aggregated rollups was 34-44x faster than aggregating `posts` live
   (about 0.4-1 s instead of 14-37 s), at the cost of a 470 s full rollup rebuild (section 6).
6. NLP inference runs at about 18,000-26,000 texts per second on a CPU; with two or more workers the
   end-to-end enrichment job is limited by database writes rather than by the models (section 7).

## Other likely questions

**Is the data real?** The posts are real tweets from the FiveThirtyEight / Clemson dataset. Engagement counts are
synthetic and labelled as such everywhere.

**Why not Spark?** The brief excluded it, and the data fits on one machine; MongoDB aggregation plus Python
multiprocessing covers the processing needs.

**What happens with a new upload?** It is stored, ingested in batches (duplicates rejected by the unique index),
enriched with NLP, and only the affected days of each rollup are recomputed with `$merge`.

**How do you know the rollups are correct?** An automated test checks that the cube and the live aggregation
return the same sentiment counts, and another checks that hashtag rollup totals match a direct count on `posts`.

**Why NMF and not LDA?** NMF on TF-IDF is fast, deterministic with a fixed seed, and tends to give readable topics
on short texts; LDA was not tried, so no claim is made that NMF is better here.
