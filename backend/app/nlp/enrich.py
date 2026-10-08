"""NLP enrichment job: adds sentiment, topic and keywords to unprocessed posts.

Data flow
  MongoDB cursor (only `_id`, `clean_text`, `language`, ordered by `_id`)
      -> batches of N posts
      -> model inference (optionally in a process pool)
      -> bulk_write of UpdateOne operations (ordered=False)

The cursor walks the `_id` index, so updating `processed` during iteration can
never make the cursor skip or revisit documents. Only one batch is in memory at
a time.

Language support (documented limitation):
  * sentiment: English only (models trained on English tweets); other languages get `sentiment: null`
  * topics/keywords: English and Russian models; other languages get topic `null`
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime

from pymongo import UpdateOne
from pymongo.database import Database

from app.config import get_settings
from app.database import mongo
from app.nlp.sentiment import load_analyzer
from app.nlp.topics import SUPPORTED_TOPIC_LANGUAGES, TopicModel

_models: dict = {}


def _init_models(sentiment_method: str) -> None:
    settings = get_settings()
    _models["sentiment"] = load_analyzer(sentiment_method, settings.model_dir)
    for lang in SUPPORTED_TOPIC_LANGUAGES:
        try:
            _models[f"topics_{lang}"] = TopicModel.load(settings.model_dir, lang)
        except FileNotFoundError:
            _models[f"topics_{lang}"] = None


def analyze_batch(docs: list[dict]) -> list[tuple]:
    """Pure inference over one batch -> list of (_id, $set fields). Runs inside workers."""
    now = datetime.now(UTC)
    results: dict = {d["_id"]: {"sentiment": None, "topic": None, "keywords": []} for d in docs}

    en = [d for d in docs if d.get("language") == "en" and d.get("clean_text")]
    if en:
        for d, s in zip(en, _models["sentiment"].analyze([d["clean_text"] for d in en]), strict=True):
            results[d["_id"]]["sentiment"] = s

    for lang in SUPPORTED_TOPIC_LANGUAGES:
        model: TopicModel | None = _models.get(f"topics_{lang}")
        group = [d for d in docs if d.get("language") == lang]
        if not model or not group:
            continue
        for d, t in zip(group, model.transform([d.get("clean_text") or "" for d in group]), strict=True):
            results[d["_id"]]["topic"] = t["topic"]
            results[d["_id"]]["keywords"] = t["keywords"]

    return [(_id, {**fields, "processed": True, "processed_at": now}) for _id, fields in results.items()]


def _batches(cursor, size: int):
    batch = []
    for doc in cursor:
        batch.append(doc)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def run_enrichment(db: Database | None = None, *, sentiment_method: str = "tfidf_logreg", batch_size: int = 5000,
                   workers: int = 1, limit: int | None = None, reprocess: bool = False, verbose: bool = False) -> dict:
    db = db if db is not None else mongo.get_db()
    coll = db[mongo.POSTS]
    query = {} if reprocess else {"processed": False}
    cursor = coll.find(query, {"clean_text": 1, "language": 1}, sort=[("_id", 1)], batch_size=batch_size,
                       no_cursor_timeout=True).hint([("_id", 1)])
    if limit:
        cursor = cursor.limit(limit)

    t0 = time.perf_counter()
    db_write_sec = 0.0
    counts: Counter = Counter()
    pool = None
    if workers > 1:
        from app.ingestion.pipeline import mp_context

        pool = mp_context().Pool(workers, initializer=_init_models, initargs=(sentiment_method,))
        results = pool.imap(analyze_batch, _batches(cursor, batch_size), chunksize=1)
    else:
        _init_models(sentiment_method)
        results = map(analyze_batch, _batches(cursor, batch_size))

    try:
        for updates in results:
            ops = [UpdateOne({"_id": _id}, {"$set": fields}) for _id, fields in updates]
            tw = time.perf_counter()
            coll.bulk_write(ops, ordered=False)
            db_write_sec += time.perf_counter() - tw
            counts["processed"] += len(ops)
            for _, f in updates:
                counts["with_sentiment"] += f["sentiment"] is not None
                counts["with_topic"] += f["topic"] is not None
            if verbose and counts["processed"] % (batch_size * 20) == 0:
                el = time.perf_counter() - t0
                print(f"  ... {counts['processed']:,} posts  {counts['processed'] / el:,.0f} posts/s", flush=True)
    finally:
        cursor.close()
        if pool is not None:
            pool.close()
            pool.join()
    elapsed = time.perf_counter() - t0
    return {
        **counts,
        "sentiment_method": sentiment_method,
        "workers": workers,
        "batch_size": batch_size,
        "elapsed_sec": round(elapsed, 2),
        "db_write_sec": round(db_write_sec, 2),
        "posts_per_sec": round(counts["processed"] / elapsed, 1) if elapsed else 0,
    }
