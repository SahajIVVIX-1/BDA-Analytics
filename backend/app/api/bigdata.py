"""Big Data Lab: Spark lake pipeline, data-lake layers and sharding results.

None of these endpoints need MongoDB: they read the measured JSON in experiments/results/ and the
Parquet folders under data/lake/. /cluster asks a mongos router for live shard status if one is running.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter

from app.config import PROJECT_DIR

router = APIRouter(prefix="/api/bigdata", tags=["big data lab"])
RESULTS_DIR = PROJECT_DIR / "experiments" / "results"
LAKE_DIR = PROJECT_DIR / "data" / "lake"
EXPERIMENTS = ("spark_pipeline", "spark_scaling", "spark_gold_summary", "lake_formats", "sharding")


def _size(path) -> tuple[int, int]:
    total, files = 0, 0
    for p in path.rglob("*"):
        if p.is_file() and not p.name.startswith((".", "_")):
            total += p.stat().st_size
            files += p.suffix == ".parquet"
    return total, files


@router.get("/results", summary="Measured Spark, data-lake and sharding experiment results")
def results():
    out = {}
    for name in EXPERIMENTS:
        p = RESULTS_DIR / f"{name}.json"
        if p.exists():
            try:
                out[name] = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
    return {"results": out, "missing": [n for n in EXPERIMENTS if n not in out]}


@router.get("/lake", summary="What is in data/lake right now (bronze / silver / gold)")
def lake():
    layers = []
    for layer in ("bronze", "silver", "gold"):
        root = LAKE_DIR / layer
        if not root.exists():
            layers.append({"layer": layer, "exists": False, "tables": []})
            continue
        tables = []
        for t in sorted(p for p in root.iterdir() if p.is_dir()):
            size, files = _size(t)
            parts = sorted({f"{m.parent.name}/{m.name}" for m in t.glob("year=*/month=*")})
            tables.append({"table": t.name, "bytes": size, "files": files, "partitions": len(parts),
                           "partition_sample": parts if len(parts) <= 6 else parts[:3] + ["…"] + parts[-3:]})
        layers.append({"layer": layer, "exists": True, "tables": tables,
                       "bytes": sum(t["bytes"] for t in tables)})
    return {"lake_dir": "data/lake", "layers": layers}


@router.get("/cluster", summary="Live status of the sharded MongoDB cluster, if a mongos is running")
def cluster():
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    uri = os.environ.get("MONGOS_URI", "mongodb://localhost:27030")
    try:
        c = MongoClient(uri, serverSelectionTimeoutMS=1500)
        shards = c.admin.command("listShards")["shards"]
        balancer = c.admin.command("balancerStatus")
        dbs = [d for d in c.config.databases.find({}, {"_id": 1, "primary": 1})]
        colls = [{"ns": x["_id"], "key": x.get("key")} for x in c.config.collections.find({}, {"_id": 1, "key": 1})
                 if not x["_id"].startswith("config.")]
        return {"online": True, "mongos": uri.split("@")[-1], "shards": [{"id": s["_id"], "host": s["host"]}
                                                                         for s in shards],
                "balancer": balancer.get("mode"), "databases": dbs, "sharded_collections": colls}
    except PyMongoError as e:
        return {"online": False, "reason": type(e).__name__,
                "hint": "Start it with: docker compose -f docker-compose.bigdata.yml up -d (see docs/bigdata.md)"}
