"""Batch ingestion pipeline: read -> validate -> normalise/clean -> dedupe -> bulk insert.

Memory use is bounded by `batch_size`: records are streamed from disk and only
one batch of documents exists in Python at a time. Duplicate detection is done
in two layers:
  * within a batch, with a small Python set;
  * across batches and across runs, by MongoDB's unique `post_id` index
    (insert_many(ordered=False) keeps inserting after a duplicate-key error and
    reports each failure, which we count).
"""

from __future__ import annotations

import multiprocessing as mp
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pymongo.database import Database
from pymongo.errors import BulkWriteError

from app.database import mongo
from app.ingestion.normalize import InvalidRecord, normalize_record
from app.ingestion.readers import expand_paths, iter_records

DUPLICATE_KEY = 11000
DOC_VALIDATION_FAILED = 121


@dataclass
class IngestionStats:
    total_read: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates_in_batch: int = 0
    duplicates_existing: int = 0
    inserted: int = 0
    write_errors: int = 0
    invalid_reasons: Counter = field(default_factory=Counter)
    cleaning: Counter = field(default_factory=Counter)
    batches: int = 0
    started: float = field(default_factory=time.perf_counter)
    elapsed_sec: float = 0.0

    @property
    def duplicates(self) -> int:
        return self.duplicates_in_batch + self.duplicates_existing

    @property
    def records_per_sec(self) -> float:
        return round(self.total_read / self.elapsed_sec, 1) if self.elapsed_sec else 0.0

    def to_dict(self) -> dict:
        return {
            "total_read": self.total_read,
            "valid": self.valid,
            "invalid": self.invalid,
            "duplicates": self.duplicates,
            "duplicates_in_batch": self.duplicates_in_batch,
            "duplicates_existing": self.duplicates_existing,
            "inserted": self.inserted,
            "write_errors": self.write_errors,
            "invalid_reasons": dict(self.invalid_reasons),
            "cleaning": dict(self.cleaning),
            "batches": self.batches,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "records_per_sec": self.records_per_sec,
        }

    def summary(self) -> str:
        return (
            f"Input:       {self.total_read:>12,}\n"
            f"Invalid:     {self.invalid:>12,}  {dict(self.invalid_reasons)}\n"
            f"Duplicates:  {self.duplicates:>12,}\n"
            f"Inserted:    {self.inserted:>12,}\n"
            f"Time:        {self.elapsed_sec:>12.1f} sec\n"
            f"Rate:        {self.records_per_sec:>12,.0f} records/sec"
        )


def _track_cleaning(stats: IngestionStats, doc: dict) -> None:
    c = stats.cleaning
    c["hashtags_extracted"] += len(doc["hashtags"])
    c["mentions_extracted"] += len(doc["mentions"])
    c["urls_removed"] += doc["url_count"]
    c["emojis_removed"] += len(doc["emojis"])
    c["posts_with_hashtags"] += bool(doc["hashtags"])
    c["retweets"] += doc["is_retweet"]
    c["missing_language"] += doc["language"] is None
    c["missing_location"] += doc["location"] is None
    c["missing_followers"] += doc["user"]["followers"] is None
    for flag in doc["quality_flags"]:
        c[f"flag_{flag}"] += 1


def _flush(coll, batch: list[dict], stats: IngestionStats) -> None:
    if not batch:
        return
    stats.batches += 1
    try:
        res = coll.insert_many(batch, ordered=False, bypass_document_validation=False)
        stats.inserted += len(res.inserted_ids)
    except BulkWriteError as e:
        details = e.details
        stats.inserted += details.get("nInserted", 0)
        for err in details.get("writeErrors", []):
            if err.get("code") == DUPLICATE_KEY:
                stats.duplicates_existing += 1
            else:
                stats.write_errors += 1
                key = "schema_validation" if err.get("code") == DOC_VALIDATION_FAILED else f"write_error_{err.get('code')}"
                stats.invalid_reasons[key] += 1


def _normalize_chunk(args: tuple) -> tuple[list[dict], Counter, int]:
    """Normalise one chunk of raw records (runs in a worker process when workers > 1)."""
    records, profile, source, job_id, now = args
    docs, invalid = [], Counter()
    for rec in records:
        try:
            docs.append(normalize_record(rec, profile, source, job_id, now=now))
        except InvalidRecord as e:
            invalid[e.reason] += 1
    return docs, invalid, len(records)


def _chunks(records: Iterable[dict], size: int, limit: int | None):
    chunk, n = [], 0
    for rec in records:
        if limit is not None and n >= limit:
            break
        chunk.append(rec)
        n += 1
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def mp_context():
    """fork where the OS has it (Linux, macOS: cheap, children inherit loaded models); spawn on Windows."""
    return mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")


def ingest_records(
    records: Iterable[dict],
    *,
    db: Database,
    profile: str,
    source: str,
    batch_size: int = 5000,
    limit: int | None = None,
    job_id: str | None = None,
    workers: int = 1,
    progress: Callable[[IngestionStats], None] | None = None,
    progress_every: int = 20,
) -> IngestionStats:
    """Ingest an iterable of raw records.

    With workers > 1, cleaning/normalisation (the CPU-bound part) runs in a process pool
    while the parent process performs the bulk inserts. Chunks stay ordered, so results
    are identical to the single-process path.
    """
    coll = db[mongo.POSTS]
    stats = IngestionStats()
    now = datetime.now(UTC)
    tasks = ((chunk, profile, source, job_id, now) for chunk in _chunks(records, batch_size, limit))

    pool = None
    if workers > 1:
        pool = mp_context().Pool(workers)
        results = pool.imap(_normalize_chunk, tasks, chunksize=1)
    else:
        results = map(_normalize_chunk, tasks)

    try:
        for docs, invalid, n_read in results:
            stats.total_read += n_read
            stats.invalid += sum(invalid.values())
            stats.invalid_reasons.update(invalid)
            stats.valid += len(docs)
            batch, batch_ids = [], set()
            for doc in docs:
                if doc["post_id"] in batch_ids:
                    stats.duplicates_in_batch += 1
                    continue
                batch_ids.add(doc["post_id"])
                _track_cleaning(stats, doc)
                batch.append(doc)
            _flush(coll, batch, stats)
            if progress and stats.batches % progress_every == 0:
                stats.elapsed_sec = time.perf_counter() - stats.started
                progress(stats)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    stats.elapsed_sec = time.perf_counter() - stats.started
    return stats


def _chain_files(paths: list[Path]):
    for p in paths:
        yield from iter_records(p)


def run_ingestion_job(
    paths: list[str | Path],
    *,
    profile: str = "ira538",
    source: str | None = None,
    batch_size: int = 5000,
    limit: int | None = None,
    db: Database | None = None,
    job_id: str | None = None,
    workers: int = 1,
    verbose: bool = False,
) -> dict:
    """Ingest files and record the job (with statistics) in `ingestion_jobs`."""
    db = db if db is not None else mongo.get_db()
    files = expand_paths(paths)
    job_id = job_id or uuid.uuid4().hex[:12]
    jobs = db[mongo.INGESTION_JOBS]
    jobs.update_one(
        {"_id": job_id},
        {"$set": {"status": "running", "files": [str(f) for f in files], "profile": profile,
                  "source": source or profile, "batch_size": batch_size, "limit": limit, "workers": workers,
                  "started_at": datetime.now(UTC)}},
        upsert=True,
    )

    def progress(stats: IngestionStats):
        jobs.update_one({"_id": job_id}, {"$set": {"stats": stats.to_dict()}})
        if verbose:
            print(f"  ... read {stats.total_read:,}  inserted {stats.inserted:,}  "
                  f"{stats.total_read / max(stats.elapsed_sec, 1e-9):,.0f} rec/s", flush=True)

    try:
        stats = ingest_records(
            _chain_files(files), db=db, profile=profile, source=source or profile,
            batch_size=batch_size, limit=limit, job_id=job_id, workers=workers, progress=progress,
        )
    except Exception as exc:  # record the failure, then re-raise
        jobs.update_one({"_id": job_id}, {"$set": {"status": "failed", "error": str(exc),
                                                     "finished_at": datetime.now(UTC)}})
        raise
    result = stats.to_dict()
    jobs.update_one({"_id": job_id}, {"$set": {"status": "completed", "stats": result,
                                                 "finished_at": datetime.now(UTC)}})
    if verbose:
        print(stats.summary())
    return {"job_id": job_id, **result}
