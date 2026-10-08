"""Tiny in-process TTL cache for analytics responses.

Analytics over millions of posts are read-heavy and change only when new data
is ingested, so caching for a short TTL removes repeated work when several
dashboard widgets (or users) ask the same question. The cache is cleared
whenever an ingestion/NLP job finishes. A multi-instance deployment would use
Redis instead; the interface would stay the same.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

_lock = threading.Lock()
_store: OrderedDict[str, tuple[float, object]] = OrderedDict()
MAX_ENTRIES = 512
stats = {"hits": 0, "misses": 0}


def get(key: str, ttl: float):
    with _lock:
        item = _store.get(key)
        if item and time.monotonic() - item[0] < ttl:
            _store.move_to_end(key)
            stats["hits"] += 1
            return item[1]
        stats["misses"] += 1
        return None


def put(key: str, value) -> None:
    with _lock:
        _store[key] = (time.monotonic(), value)
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def clear() -> None:
    with _lock:
        _store.clear()


def cached(key: str, ttl: float, fn):
    hit = get(key, ttl)
    if hit is not None:
        return hit
    value = fn()
    put(key, value)
    return value
