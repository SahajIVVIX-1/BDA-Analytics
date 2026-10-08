"""Benchmark results, index documentation and live explain() plans."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.config import PROJECT_DIR
from app.database import indexes, mongo

router = APIRouter(prefix="/api/performance", tags=["performance"])
RESULTS_DIR = PROJECT_DIR / "experiments" / "results"

# Representative dashboard queries whose plans can be inspected live.
EXPLAIN_QUERIES = {
    "sentiment_range": {"filter": {"sentiment.label": "negative",
                                   "created_at": {"$gte": "2016-10-01", "$lt": "2016-11-01"}},
                        "description": "Negative posts in October 2016 (sentiment_created index)"},
    "hashtag_lookup": {"filter": {"hashtags": "maga"}, "description": "Posts tagged #maga (multikey hashtags index)"},
    "language_range": {"filter": {"language": "de", "created_at": {"$gte": "2016-01-01", "$lt": "2017-01-01"}},
                       "description": "German posts in 2016 (language_created index)"},
    "user_timeline": {"filter": {"user.username": "TEN_GOP"}, "sort": [("created_at", -1)], "limit": 50,
                      "description": "Latest 50 posts of one account (user_created index)"},
    "text_search": {"filter": {"$text": {"$search": "election"}}, "description": "Full-text search (text index)"},
}


def _load_results() -> dict:
    out = {}
    if RESULTS_DIR.exists():
        for p in sorted(RESULTS_DIR.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
    return out


@router.get("", summary="All recorded benchmark / evaluation results")
def performance():
    db = mongo.get_db()
    runs = list(db[mongo.PERFORMANCE_TESTS].find({}, {"_id": 0}).sort("run_at", -1).limit(200))
    return {"results": _load_results(), "runs": runs,
            "note": "Every number comes from an executed experiment; see experiments/ and docs/performance.md."}


@router.get("/indexes", summary="Indexes on each collection with the reason they exist and their size")
def index_info():
    db = mongo.get_db()
    docs = indexes.index_documentation()
    sizes = {}
    for coll in {d["collection"] for d in docs}:
        try:
            sizes[coll] = db.command("collStats", coll).get("indexSizes", {})
        except Exception:  # noqa: BLE001 - collection may not exist yet
            sizes[coll] = {}
    for d in docs:
        d["size_bytes"] = sizes.get(d["collection"], {}).get(d["name"])
    return {"indexes": docs}


@router.get("/collections", summary="Document counts and storage sizes per collection")
def collections():
    db = mongo.get_db()
    out = []
    for name in sorted(db.list_collection_names()):
        s = db.command("collStats", name)
        out.append({"collection": name, "documents": s.get("count"), "size_bytes": s.get("size"),
                    "storage_bytes": s.get("storageSize"), "avg_doc_bytes": s.get("avgObjSize"),
                    "index_bytes": s.get("totalIndexSize"), "indexes": s.get("nindexes")})
    return {"collections": out}


@router.get("/explain/{name}", summary="Run explain('executionStats') for a representative query")
def explain(name: Literal["sentiment_range", "hashtag_lookup", "language_range", "user_timeline", "text_search"]):
    from datetime import datetime

    spec = EXPLAIN_QUERIES.get(name)
    if not spec:
        raise HTTPException(404, "unknown query")
    flt = json.loads(json.dumps(spec["filter"]))
    if "created_at" in flt:
        flt["created_at"] = {k: datetime.fromisoformat(v).replace(tzinfo=UTC)
                             for k, v in flt["created_at"].items()}
    db = mongo.get_db()
    cmd = {"find": mongo.POSTS, "filter": flt}
    if spec.get("sort"):
        cmd["sort"] = dict(spec["sort"])
    if spec.get("limit"):
        cmd["limit"] = spec["limit"]
    plan = db.command("explain", cmd, verbosity="executionStats")
    stats = plan["executionStats"]

    def stages(p):
        node = p.get("queryPlan", p)
        out = []
        while node:
            out.append(node.get("stage") + (f" ({node['indexName']})" if node.get("indexName") else ""))
            node = node.get("inputStage") or (node.get("inputStages") or [None])[0]
        return out

    return {"query": name, "description": spec["description"], "filter": spec["filter"],
            "winning_plan": stages(plan["queryPlanner"]["winningPlan"]),
            "n_returned": stats["nReturned"], "total_keys_examined": stats["totalKeysExamined"],
            "total_docs_examined": stats["totalDocsExamined"], "execution_ms": stats["executionTimeMillis"]}
