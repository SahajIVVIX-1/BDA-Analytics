"""The three data-lake layers, built with PySpark (medallion architecture).

  bronze  raw CSV rows stored as-is in Parquet, plus lineage columns (source file, load time)
  silver  validated, cleaned, de-duplicated posts with typed columns, partitioned by year/month
  gold    business-level aggregates that answer dashboard questions directly

Every transformation is a Spark DataFrame operation, so it runs in parallel over partitions
(one task per partition per core) and the same code would run unchanged on a cluster.
"""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from app.ingestion.cleaning import LANGUAGE_CODES, UNKNOWN_LANGUAGE_VALUES, UNKNOWN_LOCATION_VALUES
from bigdata.common import BRONZE, GOLD, SILVER

# Columns of the FiveThirtyEight IRA CSV files. Bronze keeps them all as strings: no data is
# interpreted or lost at the raw layer.
RAW_COLUMNS = [
    "external_author_id", "author", "content", "region", "language", "publish_date", "harvested_date",
    "following", "followers", "updates", "post_type", "account_type", "retweet", "account_category",
    "new_june_2018", "alt_external_id", "tweet_id", "article_url", "tco1_step1", "tco2_step1", "tco3_step1",
]
RAW_SCHEMA = T.StructType([T.StructField(c, T.StringType(), True) for c in RAW_COLUMNS])

# Same patterns as backend/app/ingestion/cleaning.py, written for Java regex. (?U) makes \w Unicode-aware
# so Cyrillic hashtags are kept, as in the Python pipeline.
URL_RE = r"https?://\S+|www\.\S+"
HASHTAG_RE = r"(?U)(?<![\w#&])#(\w*[^\W\d_]\w*)"
MENTION_RE = r"(?<![\w@])@(\w{1,15})"
RT_PREFIX_RE = r"(?i)^RT\s+@\w{1,15}:?\s*"
EMOJI_RE = ("[\\x{1F1E6}-\\x{1F1FF}\\x{1F300}-\\x{1F5FF}\\x{1F600}-\\x{1F64F}\\x{1F680}-\\x{1F6FF}\\x{1F700}-\\x{1F77F}"
            "\\x{1F780}-\\x{1F7FF}\\x{1F800}-\\x{1F8FF}\\x{1F900}-\\x{1F9FF}\\x{1FA00}-\\x{1FAFF}\\x{2600}-\\x{26FF}"
            "\\x{2700}-\\x{27BF}]")
CONTROL_RE = "[\\x{0}-\\x{8}\\x{B}-\\x{1F}\\x{7F}-\\x{9F}\\x{200B}-\\x{200F}\\x{202A}-\\x{202E}\\x{2060}-\\x{2064}\\x{FEFF}]"

GOLD_TABLES = ("daily_activity", "hashtag_daily", "top_hashtags", "account_stats", "monthly_category")


# --------------------------------------------------------------------------- bronze

def read_raw_csv(spark: SparkSession, raw_dir: Path) -> DataFrame:
    return (spark.read
            .option("header", True)
            .option("multiLine", True)   # tweets can contain line breaks inside quotes
            .option("escape", '"')
            .option("mode", "PERMISSIVE")
            .option("pathGlobFilter", "*.csv")
            .schema(RAW_SCHEMA)
            .csv(str(raw_dir)))


def build_bronze(spark: SparkSession, raw_dir: Path, out: Path = BRONZE, files: int | None = None) -> DataFrame:
    """Raw CSV -> Parquet, unchanged values plus lineage. Parquet is columnar and compressed, so every
    later read only touches the columns it needs."""
    df = (read_raw_csv(spark, raw_dir)
          .withColumn("_source_file", F.regexp_extract(F.input_file_name(), r"([^/\\]+)$", 1))
          .withColumn("_loaded_at", F.current_timestamp()))
    n = files or spark.sparkContext.defaultParallelism * 2
    df.repartition(n).write.mode("overwrite").parquet(str(out))
    return spark.read.parquet(str(out))


# --------------------------------------------------------------------------- silver

def _language_col(col):
    s = F.lower(F.trim(col))
    mapping = F.create_map(*[F.lit(x) for kv in LANGUAGE_CODES.items() for x in kv])
    slug = F.regexp_replace(F.regexp_replace(s, r"[^a-z]+", "_"), r"^_+|_+$", "")
    return (F.when(s.isNull() | s.isin(*UNKNOWN_LANGUAGE_VALUES), F.lit(None))
            .when(mapping[s].isNotNull(), mapping[s])
            .when(s.rlike(r"^[a-z]{2}$"), s)
            .otherwise(F.when(slug == "", F.lit(None)).otherwise(slug)))


def _unescape(col):
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&")):
        col = F.regexp_replace(col, a, b)
    return col


def validity(df: DataFrame) -> DataFrame:
    """Adds `_invalid`: the first reason a row is rejected (same reasons as the Python pipeline)."""
    ts = F.to_timestamp(F.trim(F.col("publish_date")), "M/d/yyyy H:mm")
    return (df.withColumn("_ts", ts)
            .withColumn("_invalid",
                        F.when(F.col("tweet_id").isNull() | (F.trim("tweet_id") == ""), "missing_id")
                        .when(F.col("content").isNull() | (F.trim("content") == ""), "empty_text")
                        .when(F.col("_ts").isNull(), "invalid_timestamp")))


def to_silver(bronze: DataFrame) -> DataFrame:
    df = validity(bronze).where(F.col("_invalid").isNull())
    content = _unescape(F.col("content"))
    post_type = F.upper(F.trim(F.col("post_type")))
    # Same order as cleaning.clean_text: drop RT prefix, URLs and mentions, keep hashtag words, drop emoji.
    body = F.regexp_replace(content, RT_PREFIX_RE, "")
    for pattern, repl in ((URL_RE, " "), (MENTION_RE, " "), (r"(?U)#(\w)", "$1"), (EMOJI_RE, " "),
                          ("[\\x{FE0F}\\x{200D}]", ""), (CONTROL_RE, ""), (r"(?U)\s+", " ")):
        body = F.regexp_replace(body, pattern, repl)
    clean = F.trim(body)
    country = F.trim(F.col("region"))
    silver = df.select(
        F.trim("tweet_id").alias("post_id"),
        F.coalesce(F.trim("alt_external_id"), F.trim("external_author_id")).alias("user_id"),
        F.coalesce(F.trim("author"), F.lit("unknown")).alias("username"),
        F.col("account_category"),
        F.col("account_type"),
        F.col("followers").cast("int").alias("followers"),
        F.col("following").cast("int").alias("following"),
        content.alias("text"),
        clean.alias("clean_text"),
        F.col("_ts").alias("created_at"),
        _language_col(F.col("language")).alias("language"),
        F.when(country.isNull() | F.lower(country).isin(*UNKNOWN_LOCATION_VALUES), F.lit(None))
         .otherwise(country).alias("country"),
        F.array_distinct(F.transform(F.regexp_extract_all(content, F.lit(HASHTAG_RE), 1), F.lower)).alias("hashtags"),
        F.array_distinct(F.transform(F.regexp_extract_all(content, F.lit(MENTION_RE), 1), F.lower)).alias("mentions"),
        F.size(F.regexp_extract_all(content, F.lit(URL_RE), 0)).alias("url_count"),
        F.when(post_type == "RETWEET", "retweet").when(post_type == "QUOTE_TWEET", "quote")
         .otherwise("original").alias("post_type"),
        F.coalesce((F.trim("retweet") == "1") | (post_type == "RETWEET") | content.rlike(RT_PREFIX_RE),
                   F.lit(False)).alias("is_retweet"),
        F.col("_source_file").alias("source_file"),
    )
    silver = silver.dropDuplicates(["post_id"])  # shuffle by post_id: one row per tweet id
    return (silver.withColumn("day", F.to_date("created_at"))
            .withColumn("year", F.year("created_at"))
            .withColumn("month", F.month("created_at")))


def build_silver(spark: SparkSession, bronze: DataFrame, out: Path = SILVER) -> DataFrame:
    """Writes silver partitioned by year/month: a query for one month reads one folder (partition pruning)."""
    (to_silver(bronze)
     .repartition("year", "month")
     .sortWithinPartitions("created_at")
     .write.mode("overwrite").partitionBy("year", "month").parquet(str(out)))
    return spark.read.parquet(str(out))


# --------------------------------------------------------------------------- gold

def gold_tables(silver: DataFrame) -> dict[str, DataFrame]:
    daily_activity = (silver.groupBy("day", "language", "country", "account_category")
                      .agg(F.count("*").alias("posts"),
                           F.sum(F.col("is_retweet").cast("int")).alias("retweets"),
                           F.approx_count_distinct("user_id").alias("active_accounts"),
                           F.sum(F.size("hashtags")).alias("hashtag_uses")))
    hashtag_daily = (silver.select("day", F.explode("hashtags").alias("hashtag"))
                     .groupBy("day", "hashtag").agg(F.count("*").alias("posts")))
    top_hashtags = (hashtag_daily.groupBy("hashtag")
                    .agg(F.sum("posts").alias("posts"), F.countDistinct("day").alias("days_active"),
                         F.min("day").alias("first_seen"), F.max("day").alias("last_seen"),
                         F.max_by("day", "posts").alias("peak_day"), F.max("posts").alias("peak_posts")))
    account_stats = (silver.groupBy("user_id", "username", "account_category")
                     .agg(F.count("*").alias("posts"),
                          F.round(F.avg(F.col("is_retweet").cast("int")), 4).alias("retweet_ratio"),
                          F.max("followers").alias("max_followers"),
                          F.min("created_at").alias("first_post"), F.max("created_at").alias("last_post"),
                          F.countDistinct("day").alias("active_days")))
    monthly_category = (silver.groupBy("year", "month", "account_category")
                        .agg(F.count("*").alias("posts"), F.countDistinct("user_id").alias("accounts")))
    return {"daily_activity": daily_activity, "hashtag_daily": hashtag_daily, "top_hashtags": top_hashtags,
            "account_stats": account_stats, "monthly_category": monthly_category}


def build_gold(spark: SparkSession, silver: DataFrame, out: Path = GOLD) -> dict[str, DataFrame]:
    written = {}
    for name, df in gold_tables(silver).items():
        path = out / name
        writer = df.coalesce(4) if name in ("daily_activity", "hashtag_daily") else df.coalesce(1)
        writer.write.mode("overwrite").parquet(str(path))
        written[name] = spark.read.parquet(str(path))
    return written
