# Big Data Lab: Spark, data lake and sharding

This part of the project adds the distributed-systems side of a Big Data course to the original single-node
MongoDB platform:

1. **Apache Spark** processes the raw CSV files in parallel (PySpark DataFrames, Spark SQL).
2. A **bronze / silver / gold data lake** stores every stage as partitioned Parquet.
3. A **sharded MongoDB cluster** (config server, three shards, a `mongos` router) holds the posts, and an
   experiment compares a hashed shard key with a ranged one.
4. The dashboard's **Big Data Lab** page shows the architecture, every measurement and the course concepts
   (5 Vs, CAP theorem, Hadoop ecosystem map) in tabs.

Every number below was measured by the scripts in `bigdata/` on the full dataset and is stored in
`experiments/results/`. The machine is recorded in each JSON file; the numbers in this document come from a
4-vCPU, 15 GiB Linux VM (Spark 4.2.0, Java 21, MongoDB 8.0.23). Re-running on another computer overwrites them.

## How to run it

### With Docker (recommended: nothing else to install)

Docker Desktop must be running. From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bigdata.ps1      # Windows
scripts/bigdata.sh                                                # macOS / Linux
```

The script builds a Spark image (Python 3.13 + Java 21 + PySpark), downloads the dataset if it is missing, runs
the Spark pipeline and benchmarks, then starts the cluster (`docker-compose.bigdata.yml`), initialises it and runs
the sharding experiment. Defaults fit Docker Desktop's ~4 GB on an 8 GB laptop (2 GB Spark driver, 0.25 GB cache
per `mongod`, 500K posts in the sharding experiment). Options: `-SkipDownload`, `-SkipBenchmarks`,
`-SkipSharding`, `-ShardDocs all`.

Single steps:

```bash
docker compose -f docker-compose.bigdata.yml build spark
docker compose -f docker-compose.bigdata.yml run --rm --no-deps spark python -m bigdata.spark.pipeline
docker compose -f docker-compose.bigdata.yml run --rm --no-deps spark python -m bigdata.spark.benchmarks all
docker compose -f docker-compose.bigdata.yml up -d
docker compose -f docker-compose.bigdata.yml run --rm spark python -m bigdata.sharding.cluster init
docker compose -f docker-compose.bigdata.yml run --rm spark python -m bigdata.sharding.experiment --size 1000000
docker compose -f docker-compose.bigdata.yml down          # add -v to delete the cluster's data
```

### Without Docker

Install Java 17 or 21 and `pip install -r bigdata/requirements.txt`, then from the project root run
`python -m bigdata.spark.pipeline` and `python -m bigdata.spark.benchmarks all`. On Linux or macOS with the
MongoDB server binaries installed, `bigdata/sharding/local_cluster.sh` starts the same cluster as plain processes.

### Getting the lake without running Spark

The Parquet output is attached to the repository's GitHub release `lake-v1` (`lake-silver.zip`, `lake-gold.zip`,
`experiment-results.zip`). Unzip them in the project root to restore `data/lake/`. `scripts/package_lake.py`
builds those archives.

## 1. Spark processing

Code: `bigdata/spark/lake.py` (transformations) and `bigdata/spark/pipeline.py` (runner).

| Stage | What Spark does | Time |
| --- | --- | --- |
| Bronze | Reads the 13 CSV files with a fixed all-string schema (multi-line quoted tweets supported), adds the source file name and load time, writes Parquet | 37.7 s |
| Validate | Gives each row a rejection reason (`missing_id`, `empty_text`, `invalid_timestamp`) or none | 3.7 s |
| Silver | Cleans text with Spark SQL regular expressions, extracts hashtags, mentions and URLs, maps languages to ISO codes, removes duplicate tweet ids (a shuffle on `post_id`), writes Parquet partitioned by `year` / `month` | 92.2 s |
| Gold | Builds five aggregate tables with `groupBy`, `explode` and `approx_count_distinct` | 12.4 s |
| **Total** | 2,945,912 rows in, 2,944,519 posts out (1 empty tweet rejected, 1,392 duplicate ids removed) | **147.3 s, 20,005 rows/s** |

The silver cleaning reproduces `backend/app/ingestion/cleaning.py` exactly: on the 1,000-row sample every post
has the same hashtags, mentions, URL count, language, country, retweet flag, timestamp and cleaned text as the
Python pipeline.

Row counts: Spark and Python's `csv` module both read 2,945,912 rows from the files downloaded on 16 Oct 2026.
The original MongoDB ingestion (8 Oct) recorded 2,946,207 rows read and 2,944,814 stored, so the upstream files
appear to have changed slightly between the two downloads; the number of duplicates (1,392) and empty tweets (1)
is identical.

### Scaling (`python -m bigdata.spark.benchmarks scaling`)

Each run starts a fresh Spark session in its own process and builds silver + gold from bronze.

| Rows | Cores | Time | Rows / s |
| --- | --- | --- | --- |
| 99,845 | 4 | 20.6 s | 4,840 |
| 500,580 | 4 | 36.2 s | 13,829 |
| 1,001,186 | 4 | 49.2 s | 20,347 |
| 2,944,519 | 4 | 112.4 s | 26,185 |
| 2,944,519 | 2 | 151.9 s | 19,379 |
| 2,944,519 | 1 | 279.3 s | 10,543 |

* **Data scaling:** 30× more rows took 5.5× longer. Spark has a fixed cost (starting the JVM, planning, scheduling
  tasks) that small inputs cannot amortise, so throughput rises with size.
* **Core scaling:** 2 cores gave a 1.84× speed-up (92% efficiency), 4 cores 2.48× (62%). The loss comes from the
  parts that do not parallelise perfectly: the shuffle for de-duplication, writing files and a VM whose 4 vCPUs
  are shared with the operating system.
* **Compared with the Python pipeline:** the original pipeline loads 9,900-11,800 records/s into MongoDB. Spark
  reaches 26,185 rows/s at full size, but it writes Parquet instead of inserting into an indexed database, so this
  compares two pipelines, not identical work.

### Execution plan

`spark_pipeline.json` stores Spark's physical plan for a one-month query. It shows the classic MapReduce shape:
`FileScan parquet` with `PartitionFilters: year = 2016, month = 10` and `ReadSchema: struct<account_category>`
(only one folder and one column are read), a `partial_count` per task (map-side combine), an
`Exchange hashpartitioning` (the shuffle) and a final `HashAggregate` (reduce).

## 2. Data lake

| Layer | Contents | Size | Files |
| --- | --- | --- | --- |
| Raw | 13 CSV files | 1.14 GB | 13 |
| Bronze | Raw rows, all strings, + lineage | 546 MB | 8 |
| Silver | Clean typed posts, partitioned `year=/month=` | 498 MB | 74 |
| Gold | `daily_activity` (52,630 rows), `hashtag_daily` (417,733), `top_hashtags` (105,227), `account_stats` (2,883), `monthly_category` (309) | 5.8 MB | 9 |

### Formats and codecs (`python -m bigdata.spark.benchmarks formats`)

The silver table written with each codec:

| Format | Size | Write time |
| --- | --- | --- |
| JSON lines (uncompressed) | 1,834 MB | 15.2 s |
| Parquet, no compression | 735 MB | 13.5 s |
| Parquet, snappy (default) | 503 MB | 11.2 s |
| Parquet, gzip | 337 MB | 23.2 s |
| Parquet, zstd | 319 MB | 14.3 s |

Columnar layout alone makes the data 2.5× smaller than JSON; zstd then gives the smallest files at almost
snappy's speed, while gzip is the slowest to write.

### Query speed: CSV vs Parquet vs partitioned Parquet (median of 3 runs)

| Query | CSV | Parquet (bronze) | Partitioned Parquet (silver) | Silver files read | Speed-up vs CSV |
| --- | --- | --- | --- | --- | --- |
| Posts per account category in October 2016 | 3.51 s | 1.01 s | 0.17 s | 1 / 74 | 20.4× |
| Top 20 hashtags in 2016 | 5.02 s | 3.03 s | 0.33 s | 12 / 74 | 15.3× |
| Posts per language, whole dataset | 2.32 s | 0.25 s | 0.27 s | 74 / 74 | 8.4× |

Three effects are visible: **column pruning** (Parquet reads one column instead of parsing all 21), **partition
pruning** (a one-month filter opens 1 of 74 folders), and **work done once in silver** (timestamps are already
parsed and hashtags already extracted, so no regular expression runs at query time). On the full scan, partitioning
gives no extra benefit, as expected.

## 3. Sharded MongoDB

Code: `bigdata/sharding/cluster.py` (initialisation), `bigdata/sharding/experiment.py`, `docker-compose.bigdata.yml`.

Topology: a config-server replica set, three shard replica sets (`shard1rs`, `shard2rs`, `shard3rs`) and one
`mongos` router; plus a standalone `mongod` as the unsharded baseline. 1,000,898 silver posts were loaded into
three collections by Spark tasks (`foreachPartition` + `insert_many(ordered=False)`), so the writes ran in parallel:

| Collection | Shard key | Load | Docs per shard |
| --- | --- | --- | --- |
| `single` | none (standalone) | 15.5 s (64,670 docs/s) | 1,000,898 |
| `hashed` | `{post_id: "hashed"}` | 19.6 s (51,160 docs/s) | 333,571 / 334,098 / 333,229 |
| `ranged` | `{created_at: 1}`, split at the terciles 2016-02-29 and 2017-01-03 | 15.2 s (65,979 docs/s) | 333,109 / 333,760 / 334,029 |

Queries (median of 5 runs; the shards a query was sent to come from `explain()`):

| Query | Standalone | Hashed | Ranged |
| --- | --- | --- | --- |
| One post by `post_id` | 0.6 ms | 0.9 ms, **1 shard** | 1.4 ms, 3 shards |
| Posts in one week (1-8 Aug 2016) | 25.8 ms | 22.7 ms, 3 shards | 36.1 ms, **1 shard** |
| Posts per account category (all) | 5.21 s | 2.32 s, 3 shards | 2.12 s, 3 shards |
| Posts per language in one week | 41.9 ms | 26.1 ms, 3 shards | 53.1 ms, **1 shard** |

What this shows:

* **Routing follows the shard key.** A filter on the shard key is *targeted* to one shard (`SINGLE_SHARD`); any
  other filter is *scatter-gather* (`SHARD_MERGE`). The hashed key targets id lookups, the ranged key targets
  date ranges.
* **Distribution needs a plan.** The hashed key spread the posts evenly with no effort. The ranged key was only
  even because it was pre-split at the data's terciles; with time-ordered inserts and no split points every new
  post would land in the last chunk (a hot shard).
* **Whole-collection aggregations ran 2.2-2.5× faster** sharded than standalone, because each shard aggregates
  its third in parallel and `mongos` only merges three small results.
* **On one machine, targeted is not always faster.** For the one-week queries the scatter-gather version was
  quicker, because three shard processes on three cores each read a third of the week. With shards on separate
  servers under concurrent load, targeting leaves the other shards free for other queries, which is the point.
* **Writes through mongos cost more** (hashed: 51K vs 65K docs/s) because every batch is split by key and
  forwarded. On separate servers that cost buys more total write capacity.

Honest limits: all shards share one machine, each replica set has a single member (no fault tolerance), and the
balancer had nothing to move because chunks were pre-placed.

## 4. Course concepts

The **Course concepts** tab maps the project to the **5 Vs** (with the measured numbers above), the **CAP
theorem** (MongoDB is CP by default: one primary per replica set, majority write concern, tunable read
preference) and the **Hadoop ecosystem** (HDFS → Parquet lake, MapReduce → Spark stages and `$group`,
Hive → Spark SQL, HBase → MongoDB, YARN → Spark's scheduler). The same material is in the report (section 7) and
the viva notes.
