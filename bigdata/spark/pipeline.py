"""Run the whole Spark lake pipeline: raw CSV -> bronze -> silver -> gold, and record what happened.

    python -m bigdata.spark.pipeline                       # from the project root, all 13 CSV files
    python -m bigdata.spark.pipeline --raw data/sample     # quick run on the 1,000-row sample
    python -m bigdata.spark.pipeline --cores 2

Writes data/lake/{bronze,silver,gold}, experiments/results/spark_pipeline.json (timings, row counts,
storage per layer) and experiments/results/spark_gold_summary.json (small extracts of the gold tables
that the dashboard's Big Data Lab page charts).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pyspark.sql import functions as F

from bigdata.common import BRONZE, GOLD, LAKE_DIR, RAW_DIR, ROOT, SILVER, dir_size, file_count, hardware, spark_session, timer, write_result
from bigdata.spark import lake


def _rows(df) -> list[dict]:
    return [r.asDict(recursive=True) for r in df.collect()]


def summarize_gold(gold: dict) -> dict:
    """Small, chart-ready extracts of each gold table (the full tables stay in Parquet)."""
    monthly = (gold["monthly_category"].where(F.col("year").isNotNull())
               .orderBy("year", "month", "account_category"))
    monthly_total = (gold["monthly_category"].groupBy("year", "month")
                     .agg(F.sum("posts").alias("posts")).orderBy("year", "month"))
    categories = (gold["monthly_category"].groupBy("account_category")
                  .agg(F.sum("posts").alias("posts")).orderBy(F.desc("posts")))
    languages = (gold["daily_activity"].groupBy("language").agg(F.sum("posts").alias("posts"))
                 .orderBy(F.desc("posts")).limit(12))
    countries = (gold["daily_activity"].groupBy("country").agg(F.sum("posts").alias("posts"))
                 .orderBy(F.desc("posts")).limit(12))
    weekday = (gold["daily_activity"].groupBy(F.date_format("day", "E").alias("weekday"),
                                              F.dayofweek("day").alias("dow"))
               .agg(F.sum("posts").alias("posts")).orderBy("dow"))
    top_tags = gold["top_hashtags"].orderBy(F.desc("posts")).limit(25)
    top_accounts = (gold["account_stats"].orderBy(F.desc("posts")).limit(15)
                    .select("username", "account_category", "posts", "retweet_ratio", "max_followers",
                            "active_days", "first_post", "last_post"))
    return {
        "row_counts": {name: df.count() for name, df in gold.items()},
        "monthly_total": _rows(monthly_total),
        "monthly_category": _rows(monthly),
        "categories": _rows(categories),
        "languages": _rows(languages),
        "countries": _rows(countries),
        "weekday": _rows(weekday),
        "top_hashtags": _rows(top_tags),
        "top_accounts": _rows(top_accounts),
    }


def run(raw_dir: Path, cores, record: bool = True) -> dict:
    spark = spark_session("lake-pipeline", cores=cores)
    t: dict = {}
    t0 = time.perf_counter()
    with timer(t, "bronze_sec"):
        bronze = lake.build_bronze(spark, raw_dir)
    bronze_rows = bronze.count()

    with timer(t, "validate_sec"):
        reasons = {r["_invalid"]: r["n"] for r in
                   lake.validity(bronze).groupBy("_invalid").agg(F.count("*").alias("n")).collect()}
    valid_rows = reasons.pop(None, 0)

    with timer(t, "silver_sec"):
        silver = lake.build_silver(spark, bronze)
    silver_rows = silver.count()

    with timer(t, "gold_sec"):
        gold = lake.build_gold(spark, silver)
    t["total_sec"] = round(time.perf_counter() - t0, 3)

    partitions = sorted({(p.parent.name, p.name) for p in SILVER.rglob("month=*")})
    layers = {
        "raw_csv": {"bytes": dir_size(raw_dir), "files": file_count(raw_dir, ".csv"), "rows": bronze_rows},
        "bronze": {"bytes": dir_size(BRONZE), "files": file_count(BRONZE), "rows": bronze_rows},
        "silver": {"bytes": dir_size(SILVER), "files": file_count(SILVER), "rows": silver_rows,
                   "partitions": len(partitions)},
        "gold": {"bytes": dir_size(GOLD), "files": file_count(GOLD),
                 "tables": {n: {"bytes": dir_size(GOLD / n), "rows": df.count()} for n, df in gold.items()}},
    }
    result = {
        "hardware": hardware(spark),
        "params": {"raw_dir": str(raw_dir.relative_to(ROOT)) if raw_dir.is_relative_to(ROOT) else str(raw_dir),
                   "master": spark.sparkContext.master,
                   "default_parallelism": spark.sparkContext.defaultParallelism,
                   "shuffle_partitions": int(spark.conf.get("spark.sql.shuffle.partitions")),
                   "lake_dir": str(LAKE_DIR.relative_to(ROOT)) if LAKE_DIR.is_relative_to(ROOT) else str(LAKE_DIR)},
        "timings": t,
        "rows": {"raw": bronze_rows, "valid": valid_rows, "invalid": reasons,
                 "duplicates_removed": valid_rows - silver_rows, "silver": silver_rows},
        "throughput_rows_per_sec": round(bronze_rows / t["total_sec"], 1),
        "layers": layers,
        "silver_partitions": [{"year": y.split("=")[1], "month": m.split("=")[1],
                               "bytes": dir_size(SILVER / y / m)} for y, m in partitions],
        "plans": {
            # Spark's physical plan for a one-month query: PartitionFilters shows only that folder is read.
            "partition_pruning": silver.where("year = 2016 AND month = 10").groupBy("account_category").count()
            ._jdf.queryExecution().executedPlan().toString(),
        },
    }
    if record:
        write_result("spark_pipeline", result)
        write_result("spark_gold_summary", {"hardware": result["hardware"], **summarize_gold(gold)})
    spark.stop()
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, default=RAW_DIR, help="folder of IRA CSV files (default data/raw/ira538)")
    ap.add_argument("--cores", default="*", help="local[N] threads (default: all cores)")
    ap.add_argument("--no-record", action="store_true", help="do not write experiments/results JSON")
    args = ap.parse_args()
    raw = args.raw if args.raw.is_absolute() else (Path.cwd() / args.raw).resolve()
    r = run(raw, args.cores, record=not args.no_record)
    print(f"{r['rows']['raw']:,} raw rows -> {r['rows']['silver']:,} silver rows in {r['timings']['total_sec']}s "
          f"({r['throughput_rows_per_sec']:,} rows/s)")


if __name__ == "__main__":
    main()
