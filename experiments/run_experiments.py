"""Big Data performance experiments.

Every number written by this script is measured when it runs; nothing is hard-coded.
Results go to experiments/results/<experiment>.json and the `performance_tests`
collection, together with the hardware/software they ran on.

Experiments
  ingestion     dataset scaling: ingest N records from CSV (N = 100K, 500K, 1M, all)
  batch         batch-size impact on ingestion throughput
  workers       parallel cleaning (1 / 2 / 4 processes)
  indexmode     load with all indexes up front vs load then build indexes
  queries       indexed vs collection scan (explain executionStats) at several sizes
  aggregations  aggregation pipeline time at several sizes + cube vs live
  nlp           sentiment / topic model throughput and end-to-end enrichment

Usage
  python experiments/run_experiments.py all
  python experiments/run_experiments.py queries aggregations --sizes 100000 500000 1000000
  python experiments/run_experiments.py ingestion --sizes 100000 500000 1000000 5000000 --data <dir>   # on your laptop

Experiments use separate databases named bench_* and drop them afterwards; the main
database is only read (queries/aggregations at full size, NLP samples).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.analytics import queries as Q  # noqa: E402
from app.analytics import rollups  # noqa: E402
from app.analytics.source import Filters  # noqa: E402
from app.database import mongo  # noqa: E402
from app.database.indexes import ensure_indexes  # noqa: E402
from app.database.schema import ensure_posts_collection, init_database  # noqa: E402
from app.ingestion.pipeline import run_ingestion_job  # noqa: E402

RESULTS = ROOT / "experiments" / "results"
DEFAULT_DATA = ROOT / "data" / "raw" / "ira538"


# --------------------------------------------------------------------------- helpers

def hardware() -> dict:
    info = {"os": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count(),
            "machine": platform.machine(), "processor": platform.processor() or None}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["processor"] = line.split(":", 1)[1].strip()
                break
        mem_kb = int(next(line for line in Path("/proc/meminfo").read_text().splitlines()
                          if line.startswith("MemTotal")).split()[1])
        info["ram_gb"] = round(mem_kb / 1024 / 1024, 1)
    except (OSError, StopIteration):
        pass
    if "ram_gb" not in info and sys.platform == "win32":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong), ("t", ctypes.c_ulonglong),
                            ("a", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            ms = MS()
            ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            info["ram_gb"] = round(ms.t / 1024**3, 1)
        except Exception:  # noqa: BLE001
            pass
    try:
        client = mongo.get_client()
        info["mongodb"] = client.server_info()["version"]
        status = client.admin.command("serverStatus")
        info["wiredtiger_cache_gb"] = round(status["wiredTiger"]["cache"]["maximum bytes configured"] / 1024**3, 2)
    except Exception:  # noqa: BLE001
        pass
    info["label"] = os.environ.get("BENCH_MACHINE_LABEL", "unlabelled machine")
    return info


def save(name: str, params: dict, results, started: float) -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    doc = {"experiment": name, "run_at": datetime.now(UTC).isoformat(), "duration_sec": round(time.perf_counter() - started, 1),
           "hardware": hardware(), "params": params, "results": results}
    (RESULTS / f"{name}.json").write_text(json.dumps(doc, indent=2, default=str))
    mongo.get_db()[mongo.PERFORMANCE_TESTS].insert_one({**doc, "run_at": datetime.now(UTC)})
    print(f"-> {RESULTS / f'{name}.json'}")
    return doc


def fresh_db(name: str):
    client = mongo.get_client()
    client.drop_database(name)
    return client[name]


def label(n: int | None, total: int) -> str:
    n = n or total
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n // 1000}K"


def median_ms(fn, runs: int = 3) -> tuple[float, list[float]]:
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(times), 1), [round(x, 1) for x in times]


def ingest_bench(data: Path, limit: int | None, batch: int, workers: int, index_mode: str) -> dict:
    db = fresh_db("bench_ingest")
    if index_mode == "upfront":
        init_database(db)
    else:
        ensure_posts_collection(db)
        db.posts.create_index("post_id", unique=True, name="uniq_post_id")
    r = run_ingestion_job([data], profile="ira538", batch_size=batch, limit=limit, db=db, workers=workers)
    out = {k: r[k] for k in ("total_read", "inserted", "duplicates", "invalid", "elapsed_sec", "records_per_sec")}
    if index_mode == "deferred":
        t = time.perf_counter()
        init_database(db)
        out["index_build_sec"] = round(time.perf_counter() - t, 2)
        out["total_sec_including_indexes"] = round(out["elapsed_sec"] + out["index_build_sec"], 2)
    else:
        out["index_build_sec"] = 0.0
        out["total_sec_including_indexes"] = out["elapsed_sec"]
    stats = db.command("collStats", "posts")
    out.update(data_mb=round(stats["size"] / 2**20, 1), storage_mb=round(stats["storageSize"] / 2**20, 1),
               index_mb=round(stats["totalIndexSize"] / 2**20, 1))
    mongo.get_client().drop_database("bench_ingest")
    return out


# --------------------------------------------------------------------------- experiments

def exp_ingestion(args):
    t0 = time.perf_counter()
    rows = []
    for n in args.sizes:
        limit = None if n == 0 else n
        print(f"[ingestion] size={limit or 'all'}", flush=True)
        r = ingest_bench(args.data, limit, 5000, args.workers, "deferred")
        rows.append({"size_requested": limit or "all", **r})
        print(f"   {r['inserted']:,} docs  {r['elapsed_sec']}s  {r['records_per_sec']:,} rec/s  +index {r['index_build_sec']}s", flush=True)
    return save("ingestion_scaling", {"batch_size": 5000, "workers": args.workers, "index_mode": "deferred",
                                      "data": str(args.data)}, rows, t0)


def exp_batch(args):
    t0 = time.perf_counter()
    rows = []
    for b in (100, 500, 1000, 5000, 20000):
        print(f"[batch] batch_size={b}", flush=True)
        r = ingest_bench(args.data, args.batch_records, b, args.workers, "deferred")
        rows.append({"batch_size": b, **{k: r[k] for k in ("inserted", "elapsed_sec", "records_per_sec")}})
        print(f"   {r['records_per_sec']:,} rec/s", flush=True)
    return save("ingestion_batch_size", {"records": args.batch_records, "workers": args.workers,
                                         "index_mode": "deferred (only unique post_id index during load)"}, rows, t0)


def exp_workers(args):
    t0 = time.perf_counter()
    rows = []
    for w in (1, 2, 4):
        print(f"[workers] workers={w}", flush=True)
        r = ingest_bench(args.data, args.batch_records, 5000, w, "deferred")
        rows.append({"workers": w, **{k: r[k] for k in ("inserted", "elapsed_sec", "records_per_sec")}})
        print(f"   {r['records_per_sec']:,} rec/s", flush=True)
    return save("ingestion_workers", {"records": args.batch_records, "batch_size": 5000}, rows, t0)


def exp_indexmode(args):
    t0 = time.perf_counter()
    rows = []
    for mode in ("upfront", "deferred"):
        print(f"[indexmode] {mode}", flush=True)
        r = ingest_bench(args.data, args.batch_records, 5000, args.workers, mode)
        rows.append({"index_mode": mode, **{k: r[k] for k in ("inserted", "elapsed_sec", "records_per_sec",
                                                              "index_build_sec", "total_sec_including_indexes")}})
        print(f"   load {r['elapsed_sec']}s + index {r['index_build_sec']}s", flush=True)
    return save("ingestion_index_mode", {"records": args.batch_records, "workers": args.workers, "batch_size": 5000}, rows, t0)


def scaled_collections(sizes: list[int]):
    """Yield (label, db) for copies of the first N enriched posts (by _id), built server-side with $out."""
    main = mongo.get_db()
    total = main.posts.estimated_document_count()
    for n in sizes:
        if n == 0 or n >= total:
            yield label(total, total), main, total
            continue
        name = f"bench_{n}"
        db = fresh_db(name)
        t = time.perf_counter()
        main.posts.aggregate([{"$sort": {"_id": 1}}, {"$limit": n}, {"$out": {"db": name, "coll": "posts"}}],
                             allowDiskUse=True)
        copy_s = time.perf_counter() - t
        t = time.perf_counter()
        ensure_indexes(db, only=mongo.POSTS)
        print(f"   prepared {name}: copy {copy_s:.1f}s, indexes {time.perf_counter() - t:.1f}s", flush=True)
        yield label(n, total), db, n
        mongo.get_client().drop_database(name)


QUERIES = {
    "sentiment_range": ({"sentiment.label": "negative",
                         "created_at": {"$gte": datetime(2016, 10, 1, tzinfo=UTC),
                                        "$lt": datetime(2016, 11, 1, tzinfo=UTC)}}, None, None,
                        "sentiment_created"),
    "hashtag_equality": ({"hashtags": "maga"}, None, None, "hashtags_created"),
    "language_range": ({"language": "de", "created_at": {"$gte": datetime(2016, 1, 1, tzinfo=UTC),
                                                          "$lt": datetime(2017, 1, 1, tzinfo=UTC)}},
                       None, None, "language_created"),
    "user_timeline_top50": ({"user.username": "TEN_GOP"}, {"created_at": -1}, 50, "user_created"),
    "country_equality": ({"location.country": "Germany"}, None, None, "country_created"),
    "date_range_1day": ({"created_at": {"$gte": datetime(2016, 11, 8, tzinfo=UTC),
                                        "$lt": datetime(2016, 11, 9, tzinfo=UTC)}}, None, None, "created_at"),
}


def explain(db, flt, sort, limit, hint):
    cmd = {"find": "posts", "filter": flt, "hint": hint}
    if sort:
        cmd["sort"] = sort
    if limit:
        cmd["limit"] = limit
    st = db.command("explain", cmd, verbosity="executionStats")["executionStats"]
    return {"ms": st["executionTimeMillis"], "docs_examined": st["totalDocsExamined"],
            "keys_examined": st["totalKeysExamined"], "n_returned": st["nReturned"]}


def exp_queries(args):
    t0 = time.perf_counter()
    rows = []
    for lbl, db, n in scaled_collections(args.sizes):
        print(f"[queries] {lbl}", flush=True)
        for name, (flt, sort, limit, idx) in QUERIES.items():
            res = {}
            for mode, hint in (("collscan", {"$natural": 1}), ("indexed", idx)):
                runs = [explain(db, flt, sort, limit, hint) for _ in range(args.runs)]
                med = statistics.median(r["ms"] for r in runs)
                res[mode] = {**runs[-1], "ms": med, "runs_ms": [r["ms"] for r in runs]}
            speedup = round(res["collscan"]["ms"] / max(res["indexed"]["ms"], 1), 1)
            rows.append({"size": lbl, "documents": n, "query": name, "index": idx,
                         **{f"{m}_{k}": v for m in res for k, v in res[m].items()},
                         "speedup": speedup})
            print(f"   {name:<22} scan {res['collscan']['ms']:>6}ms ({res['collscan']['docs_examined']:,} docs)  "
                  f"index {res['indexed']['ms']:>5}ms ({res['indexed']['docs_examined']:,} docs)", flush=True)
    return save("index_vs_collscan", {"runs": args.runs, "timing": "median executionTimeMillis from explain('executionStats')",
                                      "collscan": "hint {$natural: 1}",
                                      "cache_note": "collections fit in the WiredTiger cache; warm-cache timings"},
                rows, t0)


def agg_pipelines():
    day = {"$dateTrunc": {"date": "$created_at", "unit": "day"}}
    return {
        "sentiment_distribution": [{"$group": {"_id": "$sentiment.label", "n": {"$sum": 1}}}],
        "daily_volume": [{"$group": {"_id": day, "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}],
        "top20_hashtags_unwind": [{"$match": {"hashtags.0": {"$exists": True}}}, {"$unwind": "$hashtags"},
                                  {"$group": {"_id": "$hashtags", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}, {"$limit": 20}],
        "topic_x_sentiment": [{"$group": {"_id": {"t": "$topic.id", "s": "$sentiment.label"}, "n": {"$sum": 1}}}],
        "weekly_sentiment_en": [{"$match": {"language": "en"}},
                                {"$group": {"_id": {"w": {"$dateTrunc": {"date": "$created_at", "unit": "week"}},
                                                    "s": "$sentiment.label"}, "n": {"$sum": 1}}}],
        "country_engagement_lookup_users": [
            {"$group": {"_id": "$user.username", "posts": {"$sum": 1}, "eng": {"$sum": "$engagement.total"}}},
            {"$sort": {"eng": -1}}, {"$limit": 50},
            {"$lookup": {"from": "users", "localField": "_id", "foreignField": "_id", "as": "u"}}],
    }


def exp_aggregations(args):
    t0 = time.perf_counter()
    rows = []
    for lbl, db, n in scaled_collections(args.sizes):
        print(f"[aggregations] {lbl}", flush=True)
        if db.name != mongo.get_db().name and "users" not in db.list_collection_names():
            mongo.get_db()[mongo.USERS].aggregate([{"$out": {"db": db.name, "coll": "users"}}])
        for name, pipe in agg_pipelines().items():
            ms, runs = median_ms(lambda: list(db.posts.aggregate(pipe, allowDiskUse=True)), args.runs)
            rows.append({"size": lbl, "documents": n, "pipeline": name, "ms": ms, "runs_ms": runs})
            print(f"   {name:<34} {ms:>9.1f} ms", flush=True)

    # Pre-aggregated cube vs live aggregation on the full collection (same answers, different source).
    main = mongo.get_db()
    cube_rows = []
    for name, fn in {
        "overview_kpis": lambda mode: Q.overview(main, Filters(mode=mode)),
        "sentiment_page": lambda mode: Q.sentiment(main, Filters(mode=mode), "week"),
        "topics_page": lambda mode: Q.topics(main, Filters(mode=mode), "month"),
        "geography_page": lambda mode: Q.geography(main, Filters(mode=mode)),
        "overview_2016_english": lambda mode: Q.overview(main, Filters(mode=mode, language="en", start="2016-01-01", end="2016-12-31")),
    }.items():
        live, live_runs = median_ms(lambda: fn("live"), args.runs)
        cube, cube_runs = median_ms(lambda: fn("cube"), args.runs)
        cube_rows.append({"query": name, "live_ms": live, "cube_ms": cube, "speedup": round(live / max(cube, 0.1), 1),
                          "live_runs_ms": live_runs, "cube_runs_ms": cube_runs})
        print(f"   [cube vs live] {name:<24} live {live:>8.1f} ms  cube {cube:>7.1f} ms", flush=True)

    t = time.perf_counter()
    timings = rollups.build_all(main)
    rollup_total = round(time.perf_counter() - t, 1)
    return save("aggregation_scaling", {"runs": args.runs, "timing": "median wall-clock ms of the full aggregate() call from Python"},
                {"pipelines": rows, "cube_vs_live": cube_rows, "rollup_build": {"total_sec": rollup_total, **timings},
                 "collection_sizes": {c: main[c].estimated_document_count() for c in
                                      (mongo.POSTS, mongo.DAILY_CUBE, mongo.HASHTAG_DAILY, mongo.KEYWORD_DAILY, mongo.USERS)}}, t0)


def exp_nlp(args):
    from app.config import get_settings
    from app.nlp.enrich import run_enrichment
    from app.nlp.sentiment import TfidfLogRegAnalyzer, VaderAnalyzer
    from app.nlp.topics import TopicModel

    t0 = time.perf_counter()
    main = mongo.get_db()
    settings = get_settings()
    texts = [d["clean_text"] for d in main.posts.aggregate([{"$match": {"language": "en", "clean_text": {"$ne": ""}}},
                                                             {"$sample": {"size": args.nlp_sample}},
                                                             {"$project": {"_id": 0, "clean_text": 1}}])]
    rows = []
    models = {"vader": VaderAnalyzer(),
              "tfidf_logreg": TfidfLogRegAnalyzer.load(settings.model_dir / "sentiment_tfidf_logreg.joblib")}
    for name, m in models.items():
        ms, runs = median_ms(lambda: m.analyze(texts), args.runs)
        rows.append({"task": f"sentiment_{name}", "texts": len(texts), "ms": ms, "texts_per_sec": round(len(texts) / (ms / 1000), 1)})
        print(f"   sentiment {name:<14} {rows[-1]['texts_per_sec']:>10,.0f} texts/s", flush=True)
    topic = TopicModel.load(settings.model_dir, "en")
    ms, _ = median_ms(lambda: topic.transform(texts), args.runs)
    rows.append({"task": "topics_nmf_en_plus_keywords", "texts": len(texts), "ms": ms, "texts_per_sec": round(len(texts) / (ms / 1000), 1)})
    print(f"   topics nmf          {rows[-1]['texts_per_sec']:>10,.0f} texts/s", flush=True)

    # End-to-end enrichment (read from MongoDB -> models -> bulk_write) on a copy of N posts.
    e2e = []
    name = "bench_nlp"
    db = fresh_db(name)
    main.posts.aggregate([{"$sort": {"_id": 1}}, {"$limit": args.nlp_e2e}, {"$out": {"db": name, "coll": "posts"}}])
    ensure_indexes(db, only=mongo.POSTS, include_text=False)
    for w in (1, 2, 4):
        r = run_enrichment(db, workers=w, reprocess=True, batch_size=5000)
        e2e.append({"workers": w, "posts": r["processed"], "elapsed_sec": r["elapsed_sec"], "db_write_sec": r["db_write_sec"],
                    "posts_per_sec": r["posts_per_sec"]})
        print(f"   end-to-end workers={w}: {r['posts_per_sec']:,} posts/s "
              f"(db writes {r['db_write_sec']}s of {r['elapsed_sec']}s)", flush=True)
    mongo.get_client().drop_database(name)
    return save("nlp_throughput", {"sample": len(texts), "e2e_posts": args.nlp_e2e, "runs": args.runs},
                {"models": rows, "end_to_end": e2e}, t0)


EXPERIMENTS = {"ingestion": exp_ingestion, "batch": exp_batch, "workers": exp_workers, "indexmode": exp_indexmode,
               "queries": exp_queries, "aggregations": exp_aggregations, "nlp": exp_nlp}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiments", nargs="+", choices=[*EXPERIMENTS, "all"])
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="raw CSV folder for ingestion experiments")
    ap.add_argument("--sizes", type=int, nargs="+", default=[100_000, 500_000, 1_000_000, 0],
                    help="dataset sizes; 0 = everything")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch-records", type=int, default=300_000, help="records for batch/workers/indexmode runs")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--nlp-sample", type=int, default=20_000)
    ap.add_argument("--nlp-e2e", type=int, default=200_000)
    args = ap.parse_args()
    names = list(EXPERIMENTS) if "all" in args.experiments else args.experiments
    for n in names:
        EXPERIMENTS[n](args)


if __name__ == "__main__":
    main()
