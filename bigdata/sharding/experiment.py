"""Sharding experiment: the same posts in a standalone mongod and in a 3-shard cluster with two shard keys.

    python -m bigdata.sharding.experiment --size 1000000     # needs the cluster (cluster.py init) and silver

Collections compared
  single   standalone mongod, no sharding (baseline)
  hashed   shard key {post_id: "hashed"}  -> even spread, but date-range queries go to every shard
  ranged   shard key {created_at: 1}, pre-split at the data's terciles -> date-range queries hit one shard

Loading is done by Spark: each partition of the silver table is written by its own task with
insert_many(ordered=False), so N cores write in parallel through mongos.

Measured: load time, documents and chunks per shard, and for each query the shards it was routed to
(from explain()), the plan stage (SINGLE_SHARD vs SHARD_MERGE) and the median time of 5 runs.
All shards run on one machine here, so this shows data distribution and query routing, not the
extra CPU and disk that separate shard servers would add.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from datetime import UTC, datetime

from pymongo import ASCENDING, MongoClient

from bigdata.common import SILVER, hardware, spark_session, write_result
from bigdata.sharding.cluster import MONGOS_URI, SINGLE_URI

DB = "bigdata_sharding"
FIELDS = ["post_id", "user_id", "username", "account_category", "created_at", "language", "country",
          "hashtags", "mentions", "is_retweet", "followers", "clean_text"]


def _write_partition(rows, uri: str, coll: str):
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    client = MongoClient(uri)
    c = client[DB][coll]
    batch = []
    for r in rows:
        batch.append(r.asDict())
        if len(batch) == 5000:
            c.insert_many(batch, ordered=False)
            batch = []
    if batch:
        c.insert_many(batch, ordered=False)
    client.close()


def load(df, uri: str, coll: str) -> float:
    t = time.perf_counter()
    df.foreachPartition(lambda rows: _write_partition(rows, uri, coll))
    return round(time.perf_counter() - t, 3)


def shard_distribution(mongos: MongoClient, coll: str) -> list[dict]:
    ns = f"{DB}.{coll}"
    stats = mongos[DB][coll].aggregate([{"$collStats": {"storageStats": {}}}])
    by_shard = {s["shard"]: {"shard": s["shard"], "docs": s["storageStats"]["count"],
                             "bytes": s["storageStats"]["size"]} for s in stats}
    uuid = mongos.config.collections.find_one({"_id": ns})["uuid"]
    for row in mongos.config.chunks.aggregate([{"$match": {"uuid": uuid}},
                                               {"$group": {"_id": "$shard", "n": {"$sum": 1}}}]):
        by_shard.setdefault(row["_id"], {"shard": row["_id"], "docs": 0, "bytes": 0})["chunks"] = row["n"]
    return sorted(by_shard.values(), key=lambda r: r["shard"])


def _shards_from_explain(ex: dict) -> tuple[list[str], str]:
    qp = ex.get("queryPlanner", {})
    wp = qp.get("winningPlan", {})
    if "shards" in wp:
        return [s["shardName"] for s in wp["shards"]], wp.get("stage", "")
    if "shards" in ex:  # aggregate explain
        return list(ex["shards"].keys()), ex.get("splitPipeline") and "SHARD_MERGE (split pipeline)" or \
            "SINGLE_SHARD" if len(ex["shards"]) == 1 else "SHARD_MERGE"
    return [], wp.get("stage", "standalone")


def run_queries(db, sample_post_id: str, week_start: datetime, week_end: datetime, sharded: bool) -> list[dict]:
    coll_queries = {
        "point_lookup": ("Find one post by post_id", "find", {"post_id": sample_post_id}),
        "one_week": ("Posts in one week (date range)", "find",
                     {"created_at": {"$gte": week_start, "$lt": week_end}}),
        "category_totals": ("Posts per account category (whole collection)", "aggregate",
                            [{"$group": {"_id": "$account_category", "n": {"$sum": 1}}}]),
        "week_by_language": ("Posts per language in one week", "aggregate",
                             [{"$match": {"created_at": {"$gte": week_start, "$lt": week_end}}},
                              {"$group": {"_id": "$language", "n": {"$sum": 1}}}]),
    }
    out = []
    for key, (desc, kind, q) in coll_queries.items():
        def run():
            if kind == "find":
                return len(list(db.find(q, {"_id": 1})))
            return len(list(db.aggregate(q)))
        run()  # warm cache
        times = []
        for _ in range(5):
            t = time.perf_counter()
            n = run()
            times.append((time.perf_counter() - t) * 1000)
        if kind == "find":
            ex = db.database.command("explain", {"find": db.name, "filter": q}, verbosity="queryPlanner")
        else:
            ex = db.database.command("explain", {"aggregate": db.name, "pipeline": q, "cursor": {}},
                                     verbosity="queryPlanner")
        shards, stage = _shards_from_explain(ex) if sharded else ([], "standalone")
        out.append({"query": key, "description": desc, "results": n, "median_ms": round(statistics.median(times), 2),
                    "shards_targeted": shards, "n_shards": len(shards) if sharded else 1, "stage": stage})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--size", default="1000000", help="number of silver posts to load, or 'all'")
    ap.add_argument("--mongos", default=MONGOS_URI)
    ap.add_argument("--single", default=SINGLE_URI)
    args = ap.parse_args()

    spark = spark_session("sharding-load")
    from pyspark.sql import functions as F

    silver = spark.read.parquet(str(SILVER)).select(*FIELDS)
    total = silver.count()
    if args.size != "all" and int(args.size) < total:
        silver = silver.sample(fraction=int(args.size) / total, seed=7)
    silver = silver.repartition(spark.sparkContext.defaultParallelism * 2).cache()
    n = silver.count()
    # Split points at the 1/3 and 2/3 quantiles of created_at give each shard about a third of the posts.
    q1, q2 = silver.select(F.unix_timestamp("created_at").alias("t")).approxQuantile("t", [1 / 3, 2 / 3], 0.001)
    splits = [datetime.fromtimestamp(q, UTC).replace(tzinfo=None) for q in (q1, q2)]
    sample_id = silver.select("post_id").first()["post_id"]

    mongos = MongoClient(args.mongos)
    single = MongoClient(args.single)
    for c in (mongos, single):
        c.drop_database(DB)
    shards = sorted(s["_id"] for s in mongos.admin.command("listShards")["shards"])
    mongos.admin.command("enableSharding", DB, primaryShard=shards[0])
    mongos.admin.command("shardCollection", f"{DB}.hashed", key={"post_id": "hashed"})
    mongos.admin.command("shardCollection", f"{DB}.ranged", key={"created_at": 1})
    for s in splits:
        mongos.admin.command("split", f"{DB}.ranged", middle={"created_at": s})
    for shard, bound in zip(shards[1:], splits, strict=False):
        mongos.admin.command("moveChunk", f"{DB}.ranged", find={"created_at": bound}, to=shard,
                             _waitForDelete=True)

    loads = {}
    loads["single"] = load(silver, args.single, "single")
    loads["hashed"] = load(silver, args.mongos, "hashed")
    loads["ranged"] = load(silver, args.mongos, "ranged")
    for name, sec in loads.items():
        print(f"  load {name:7} {n:,} docs in {sec}s ({n / sec:,.0f} docs/s)")

    # Secondary indexes so every query below can use an index in every layout.
    single[DB]["single"].create_index([("created_at", ASCENDING)])
    single[DB]["single"].create_index([("post_id", ASCENDING)])
    mongos[DB]["hashed"].create_index([("created_at", ASCENDING)])
    mongos[DB]["ranged"].create_index([("post_id", ASCENDING)])

    mid = splits[0] + (splits[1] - splits[0]) / 2
    week_start = datetime(mid.year, mid.month, mid.day)
    week_end = datetime.fromtimestamp(week_start.timestamp() + 7 * 86400)
    collections = {"single": (single[DB]["single"], False), "hashed": (mongos[DB]["hashed"], True),
                   "ranged": (mongos[DB]["ranged"], True)}
    strategies = []
    for name, (coll, sharded) in collections.items():
        strategies.append({
            "name": name,
            "shard_key": {"single": None, "hashed": {"post_id": "hashed"}, "ranged": {"created_at": 1}}[name],
            "load_sec": loads[name], "docs_per_sec": round(n / loads[name], 1),
            "distribution": shard_distribution(mongos, name) if sharded else
            [{"shard": "standalone", "docs": coll.estimated_document_count(), "chunks": None}],
            "queries": run_queries(coll, sample_id, week_start, week_end, sharded),
        })
        print(f"  {name}: " + ", ".join(f"{q['query']}={q['median_ms']}ms/{q['n_shards']} shard(s)"
                                        for q in strategies[-1]["queries"]))
    hw = hardware(spark)
    hw["mongodb"] = mongos.server_info()["version"]
    write_result("sharding", {
        "hardware": hw,
        "params": {"docs": n, "shards": shards, "ranged_split_points": splits,
                   "query_week": [week_start, week_end], "runs_per_query": 5, "statistic": "median"},
        "topology": {"config_servers": 1, "shards": len(shards), "routers": 1,
                     "replica_set_members_per_shard": 1},
        "strategies": strategies,
        "note": "All shards share one machine, so timings show routing overhead and data layout, "
                "not the throughput separate servers would add.",
    })
    spark.stop()


if __name__ == "__main__":
    main()
