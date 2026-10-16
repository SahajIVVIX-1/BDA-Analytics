"""Spark and data-lake experiments. Every number is measured when this runs.

    python -m bigdata.spark.benchmarks scaling     # dataset size x cores, bronze -> silver -> gold
    python -m bigdata.spark.benchmarks formats     # CSV vs Parquet: storage, codecs, query time, partition pruning
    python -m bigdata.spark.benchmarks all

Needs the lake from `python -m bigdata.spark.pipeline` (bronze and silver). Each scaling run starts a fresh
Spark session in its own process so caches and JIT warm-up from one run cannot help the next.
Results: experiments/results/spark_scaling.json and experiments/results/lake_formats.json.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bigdata.common import (
    BRONZE,
    LAKE_DIR,
    RAW_DIR,
    RESULTS,
    ROOT,
    SILVER,
    dir_size,
    file_count,
    hardware,
    reset_dir,
    spark_session,
    write_result,
)

SIZES = [100_000, 500_000, 1_000_000, None]  # None = all rows
CORES = sorted({c for c in (1, 2, 4, os.cpu_count() or 1) if c <= (os.cpu_count() or 1)})


# --------------------------------------------------------------------------- scaling

def _one_scaling_run(size: int | None, cores: int) -> dict:
    """Runs inside a child process: sample `size` bronze rows, build silver + gold, time each stage."""
    from bigdata.spark import lake

    spark = spark_session(f"scaling-{size}-{cores}", cores=cores)
    bronze = spark.read.parquet(str(BRONZE))
    total = bronze.count()
    if size and size < total:
        # sample() keeps every partition (and so every core) busy; limit() would collapse to one partition.
        bronze = bronze.sample(fraction=size / total, seed=42)
    out = Path(tempfile.mkdtemp(prefix="scaling_", dir=LAKE_DIR))
    t = {}
    try:
        t0 = time.perf_counter()
        (lake.to_silver(bronze).repartition("year", "month")
         .write.mode("overwrite").partitionBy("year", "month").parquet(str(out / "silver")))
        t["silver_sec"] = round(time.perf_counter() - t0, 3)
        silver = spark.read.parquet(str(out / "silver"))
        rows = silver.count()
        t1 = time.perf_counter()
        for name, df in lake.gold_tables(silver).items():
            df.write.mode("overwrite").parquet(str(out / "gold" / name))
        t["gold_sec"] = round(time.perf_counter() - t1, 3)
        t["total_sec"] = round(t["silver_sec"] + t["gold_sec"], 3)
        tasks = silver.rdd.getNumPartitions()
    finally:
        reset_dir(out)
        spark.stop()
    return {"size_requested": size or "all", "rows": rows, "cores": cores, **t,
            "rows_per_sec": round(rows / t["total_sec"], 1), "silver_read_partitions": tasks}


def _run_child(size, cores) -> dict:
    code = ("import json,sys; from bigdata.spark.benchmarks import _one_scaling_run as r; "
            f"print('RESULT' + json.dumps(r({size!r}, {cores})))")
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT"):
            return json.loads(line[6:])
    raise RuntimeError(proc.stderr[-3000:])


def scaling(sizes=SIZES, cores=CORES) -> dict:
    runs = []
    max_cores = max(cores)
    for size in sizes:                                  # data scaling at full parallelism
        r = _run_child(size, max_cores)
        print(f"  size={r['size_requested']:>9} cores={r['cores']} {r['total_sec']:>8}s {r['rows_per_sec']:>10,.0f} rows/s")
        runs.append(r)
    for c in cores:                                     # strong scaling: same data, more cores
        if c == max_cores:
            continue
        r = _run_child(None, c)
        print(f"  size={r['size_requested']:>9} cores={r['cores']} {r['total_sec']:>8}s {r['rows_per_sec']:>10,.0f} rows/s")
        runs.append(r)
    full = {r["cores"]: r["total_sec"] for r in runs if r["size_requested"] == "all"}
    base = full.get(min(full))
    speedup = [{"cores": c, "total_sec": s, "speedup": round(base / s, 2),
                "efficiency": round(base / s / (c / min(full)), 2)} for c, s in sorted(full.items())]
    python_ref = None
    ref = RESULTS / "ingestion_scaling.json"
    if ref.exists():  # the original single-process-insert Python pipeline, for comparison
        d = json.loads(ref.read_text())
        python_ref = [{"size_requested": r["size_requested"], "rows": r["inserted"], "elapsed_sec": r["elapsed_sec"],
                       "rows_per_sec": r["records_per_sec"]} for r in d["results"]]
    import pyspark
    hw = hardware()
    hw["spark"] = pyspark.__version__
    return write_result("spark_scaling", {"hardware": hw, "runs": runs, "speedup": speedup,
                                          "python_pipeline_reference": python_ref,
                                          "note": "Spark runs read bronze Parquet and write silver + gold Parquet. "
                                                  "The Python reference reads CSV and inserts into MongoDB with "
                                                  "deferred indexes, so it is a comparison of pipelines, not of "
                                                  "identical work."})


# --------------------------------------------------------------------------- formats

def _median_time(fn, repeat: int = 3) -> tuple[float, object]:
    times, out = [], None
    for _ in range(repeat):
        t = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t)
    return round(statistics.median(times), 3), out


def formats(raw_dir: Path = RAW_DIR) -> dict:
    from pyspark.sql import functions as F

    from bigdata.spark import lake

    spark = spark_session("lake-formats")
    csv = lake.read_raw_csv(spark, raw_dir)
    bronze = spark.read.parquet(str(BRONZE))
    silver = spark.read.parquet(str(SILVER))

    # Storage: the same silver data written with different codecs.
    codecs = []
    tmp = Path(tempfile.mkdtemp(prefix="codecs_", dir=LAKE_DIR))
    try:
        for codec in ("none", "snappy", "gzip", "zstd"):
            path = tmp / codec
            t = time.perf_counter()
            silver.write.mode("overwrite").option("compression", codec).parquet(str(path))
            codecs.append({"codec": codec, "bytes": dir_size(path), "write_sec": round(time.perf_counter() - t, 3)})
            print(f"  codec {codec:6} {codecs[-1]['bytes'] / 1e6:8.1f} MB")
        jpath = tmp / "jsonl"
        t = time.perf_counter()
        silver.drop("year", "month").write.mode("overwrite").json(str(jpath))
        codecs.append({"codec": "json (uncompressed)", "bytes": dir_size(jpath),
                       "write_sec": round(time.perf_counter() - t, 3)})
    finally:
        reset_dir(tmp)

    raw_bytes = dir_size(raw_dir)
    storage = [{"layer": "Raw CSV", "format": "CSV", "bytes": raw_bytes, "files": file_count(raw_dir, ".csv")},
               {"layer": "Bronze", "format": "Parquet (snappy)", "bytes": dir_size(BRONZE), "files": file_count(BRONZE)},
               {"layer": "Silver", "format": "Parquet (snappy), partitioned year/month", "bytes": dir_size(SILVER),
                "files": file_count(SILVER)}]

    ts_csv = F.to_timestamp(F.trim("publish_date"), "M/d/yyyy H:mm")
    queries = {
        "category_oct_2016": {
            "description": "Posts per account category in October 2016",
            "csv": lambda: csv.where((F.year(ts_csv) == 2016) & (F.month(ts_csv) == 10))
            .groupBy("account_category").count().collect(),
            "parquet": lambda: bronze.where((F.year(ts_csv) == 2016) & (F.month(ts_csv) == 10))
            .groupBy("account_category").count().collect(),
            "partitioned": lambda: silver.where("year = 2016 AND month = 10").groupBy("account_category").count()
            .collect(),
            "partitions_read": lambda: file_count(SILVER / "year=2016" / "month=10"),
        },
        "top_hashtags_2016": {
            "description": "Top 20 hashtags in 2016",
            "csv": lambda: csv.where(F.year(ts_csv) == 2016)
            .select(F.explode(F.regexp_extract_all("content", F.lit(lake.HASHTAG_RE), 1)).alias("h"))
            .groupBy(F.lower("h")).count().orderBy(F.desc("count")).limit(20).collect(),
            "parquet": lambda: bronze.where(F.year(ts_csv) == 2016)
            .select(F.explode(F.regexp_extract_all("content", F.lit(lake.HASHTAG_RE), 1)).alias("h"))
            .groupBy(F.lower("h")).count().orderBy(F.desc("count")).limit(20).collect(),
            "partitioned": lambda: silver.where("year = 2016").select(F.explode("hashtags").alias("h"))
            .groupBy("h").count().orderBy(F.desc("count")).limit(20).collect(),
            "partitions_read": lambda: file_count(SILVER / "year=2016"),
        },
        "posts_by_language": {
            "description": "Posts per language, whole dataset (full scan, one column)",
            "csv": lambda: csv.groupBy("language").count().collect(),
            "parquet": lambda: bronze.groupBy("language").count().collect(),
            "partitioned": lambda: silver.groupBy("language").count().collect(),
            "partitions_read": lambda: file_count(SILVER),
        },
    }
    qres = []
    for key, q in queries.items():
        row = {"query": key, "description": q["description"], "silver_files_read": q["partitions_read"](),
               "silver_files_total": file_count(SILVER)}
        for fmt in ("csv", "parquet", "partitioned"):
            row[f"{fmt}_sec"], _ = _median_time(q[fmt])
        row["speedup_vs_csv"] = round(row["csv_sec"] / row["partitioned_sec"], 1)
        print(f"  {key:20} csv {row['csv_sec']:7}s parquet {row['parquet_sec']:7}s "
              f"partitioned {row['partitioned_sec']:7}s")
        qres.append(row)
    result = {"hardware": hardware(spark), "storage": storage, "codecs": codecs, "queries": qres,
              "params": {"repeat": 3, "statistic": "median",
                         "lake_dir": str(LAKE_DIR.relative_to(ROOT)) if LAKE_DIR.is_relative_to(ROOT) else str(LAKE_DIR)}}
    spark.stop()
    return write_result("lake_formats", result)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("experiments", nargs="+", choices=["scaling", "formats", "all"])
    ap.add_argument("--sizes", nargs="*", type=int, help="dataset sizes for scaling (default 100K 500K 1M all)")
    ap.add_argument("--cores", nargs="*", type=int, default=CORES)
    args = ap.parse_args()
    todo = {"scaling", "formats"} if "all" in args.experiments else set(args.experiments)
    if "scaling" in todo:
        print("scaling")
        scaling((args.sizes + [None]) if args.sizes else SIZES, args.cores)
    if "formats" in todo:
        print("formats")
        formats()


if __name__ == "__main__":
    main()
