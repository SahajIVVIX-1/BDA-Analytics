"""Background ingestion jobs started from the API.

A job runs in a worker thread: ingestion -> (optional) NLP enrichment of the new
posts -> (optional) incremental rollup refresh for the affected days. Its state
lives in the `ingestion_jobs` collection, so it survives API restarts for
reporting and can be polled by the dashboard.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.analytics import rollups
from app.database import mongo
from app.database.schema import init_database
from app.ingestion.pipeline import run_ingestion_job
from app.services import cache

_running: dict[str, threading.Thread] = {}


def start_job(paths: list[Path], *, profile: str, source: str | None, batch_size: int, limit: int | None,
              run_nlp: bool, refresh_rollups: bool) -> str:
    job_id = uuid.uuid4().hex[:12]
    db = mongo.get_db()
    db[mongo.INGESTION_JOBS].insert_one({"_id": job_id, "status": "queued", "files": [str(p) for p in paths],
                                         "profile": profile, "source": source or profile,
                                         "started_at": datetime.now(UTC)})
    t = threading.Thread(target=_run, name=f"ingest-{job_id}", daemon=True,
                         args=(job_id, paths, profile, source, batch_size, limit, run_nlp, refresh_rollups))
    _running[job_id] = t
    t.start()
    return job_id


def _run(job_id, paths, profile, source, batch_size, limit, run_nlp, refresh_rollups) -> None:
    db = mongo.get_db()
    jobs = db[mongo.INGESTION_JOBS]
    try:
        init_database(db)
        run_ingestion_job(paths, profile=profile, source=source, batch_size=batch_size, limit=limit, db=db,
                          job_id=job_id)
        if run_nlp:
            from app.nlp.enrich import run_enrichment

            jobs.update_one({"_id": job_id}, {"$set": {"status": "nlp"}})
            nlp = run_enrichment(db, batch_size=batch_size)
            jobs.update_one({"_id": job_id}, {"$set": {"nlp": nlp}})
        if refresh_rollups:
            jobs.update_one({"_id": job_id}, {"$set": {"status": "rollups"}})
            rng = list(db[mongo.POSTS].aggregate([
                {"$match": {"ingestion_job_id": job_id}},
                {"$group": {"_id": None, "first": {"$min": "$created_at"}, "last": {"$max": "$created_at"}}}]))
            if rng:
                start = rng[0]["first"].replace(hour=0, minute=0, second=0, microsecond=0)
                end = rng[0]["last"].replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                # Incremental: only the days touched by this job are recomputed.
                timings = rollups.build_all(db, start=start, end=end)
                jobs.update_one({"_id": job_id}, {"$set": {"rollups": {"start": start, "end": end, **timings}}})
        jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "finished_at": datetime.now(UTC)}})
    except Exception as exc:  # noqa: BLE001 - job state must record any failure
        jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "error": str(exc)[:500],
                                                     "finished_at": datetime.now(UTC)}})
    finally:
        cache.clear()
        _running.pop(job_id, None)
