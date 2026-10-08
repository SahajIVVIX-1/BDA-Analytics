"""MongoDB connection management.

A single `MongoClient` is shared per process (PyMongo clients are thread-safe and
maintain their own connection pool).
"""

from __future__ import annotations

import threading

from pymongo import MongoClient
from pymongo.database import Database

from app.config import get_settings

_client: MongoClient | None = None
_lock = threading.Lock()

# Collection names, kept in one place.
POSTS = "posts"
INGESTION_JOBS = "ingestion_jobs"
DAILY_CUBE = "daily_cube"
HOURLY_CUBE = "hourly_cube"
HASHTAG_DAILY = "hashtag_daily"
KEYWORD_DAILY = "keyword_daily"
TOPICS = "topics"
USERS = "users"
PERFORMANCE_TESTS = "performance_tests"
MODEL_RUNS = "model_runs"


def get_client() -> MongoClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                s = get_settings()
                _client = MongoClient(
                    s.mongo_uri,
                    serverSelectionTimeoutMS=s.mongo_timeout_ms,
                    tz_aware=True,
                    appname="social-media-big-data",
                )
    return _client


def get_db(name: str | None = None) -> Database:
    return get_client()[name or get_settings().mongo_db]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
