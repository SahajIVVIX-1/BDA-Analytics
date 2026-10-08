"""Index definitions for every collection, with the reason each one exists.

Compound indexes follow MongoDB's ESR guideline (Equality fields first, then the
Sort field, then Range fields). Most dashboard queries are "equality filter on a
category + range on `created_at`", which is why `created_at` is the trailing key
of most compound indexes.

The `reason` strings are also exposed through the API (`/api/performance/indexes`)
and documented in docs/database.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.database import Database

from app.database import mongo


@dataclass(frozen=True)
class IndexSpec:
    collection: str
    keys: list[tuple[str, int | str]]
    name: str
    reason: str
    options: dict = field(default_factory=dict)


POST_INDEXES: list[IndexSpec] = [
    IndexSpec(
        mongo.POSTS,
        [("post_id", ASCENDING)],
        "uniq_post_id",
        "Enforces one document per source post. Bulk inserts with ordered=False rely on "
        "this to reject duplicates server-side (error 11000) instead of checking in Python.",
        {"unique": True},
    ),
    IndexSpec(
        mongo.POSTS,
        [("created_at", ASCENDING)],
        "created_at",
        "Date-range filters and chronological sorting (Data Explorer, time series with no other filter).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("sentiment.label", ASCENDING), ("created_at", ASCENDING)],
        "sentiment_created",
        "Equality on sentiment + range on date (sentiment over time, explorer sentiment filter).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("language", ASCENDING), ("created_at", ASCENDING)],
        "language_created",
        "Equality on language + date range (language analytics, explorer language filter).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("location.country", ASCENDING), ("created_at", ASCENDING)],
        "country_created",
        "Equality on country + date range (geography page, explorer location filter).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("hashtags", ASCENDING), ("created_at", ASCENDING)],
        "hashtags_created",
        "Multikey index on the hashtags array: find posts containing a hashtag, ordered by date.",
    ),
    IndexSpec(
        mongo.POSTS,
        [("topic.id", ASCENDING), ("created_at", ASCENDING)],
        "topic_created",
        "Equality on topic + date range (topic drill-down, explorer topic filter).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("user.username", ASCENDING), ("created_at", DESCENDING)],
        "user_created",
        "A single account's timeline, newest first (user behaviour analysis).",
    ),
    IndexSpec(
        mongo.POSTS,
        [("text_hash", ASCENDING)],
        "text_hash",
        "Groups identical cleaned texts; used to detect copy-paste (spam-like) campaigns.",
    ),
    IndexSpec(
        mongo.POSTS,
        [("processed", ASCENDING)],
        "unprocessed_partial",
        "Partial index containing only documents still waiting for NLP enrichment, so the "
        "NLP worker finds its next batch without scanning millions of processed posts.",
        {"partialFilterExpression": {"processed": False}},
    ),
    IndexSpec(
        mongo.POSTS,
        [("engagement.total", DESCENDING)],
        "engagement_total",
        "Top-N posts by engagement without sorting the whole collection in memory.",
        {"sparse": True},
    ),
    IndexSpec(
        mongo.POSTS,
        [("clean_text", TEXT)],
        "text_search",
        "Full-text keyword search in the Data Explorer. default_language='none' because the "
        "corpus is multilingual; language_override points at a field that does not exist so "
        "the ISO `language` field is not misread as a stemming language.",
        {"default_language": "none", "language_override": "text_search_language"},
    ),
]

AUX_INDEXES: list[IndexSpec] = [
    IndexSpec(mongo.DAILY_CUBE,
              [("day", ASCENDING), ("language", ASCENDING), ("country", ASCENDING), ("sentiment", ASCENDING),
               ("topic_id", ASCENDING)], "uniq_cube_cell",
              "Upsert key for $merge (one row per cube cell); its `day` prefix also serves date-range scans.",
              {"unique": True}),
    IndexSpec(mongo.DAILY_CUBE, [("topic_id", ASCENDING), ("day", ASCENDING)], "cube_topic_day",
              "Topic timelines/growth from the cube without scanning other topics."),
    IndexSpec(mongo.HOURLY_CUBE, [("hour", ASCENDING), ("language", ASCENDING), ("sentiment", ASCENDING)],
              "uniq_hour_cell", "Upsert key for $merge; hour-range scans for hourly charts and the activity heatmap.",
              {"unique": True}),
    IndexSpec(mongo.HASHTAG_DAILY, [("day", ASCENDING), ("hashtag", ASCENDING)], "uniq_day_hashtag",
              "Upsert key for $merge and window scans for trend detection.", {"unique": True}),
    IndexSpec(mongo.HASHTAG_DAILY, [("hashtag", ASCENDING), ("day", ASCENDING)], "hashtag_day",
              "Timeline for a single hashtag."),
    IndexSpec(mongo.KEYWORD_DAILY, [("day", ASCENDING), ("language", ASCENDING), ("keyword", ASCENDING)],
              "uniq_day_lang_keyword", "Upsert key for $merge and window scans for keyword trends.", {"unique": True}),
    IndexSpec(mongo.KEYWORD_DAILY, [("keyword", ASCENDING), ("day", ASCENDING)], "keyword_day",
              "Timeline for a single keyword."),
    IndexSpec(mongo.USERS, [("posts", DESCENDING)], "users_posts", "Most active accounts first."),
    IndexSpec(mongo.INGESTION_JOBS, [("started_at", DESCENDING)], "started_at",
              "Most-recent-first job listing."),
    IndexSpec(mongo.PERFORMANCE_TESTS, [("experiment", ASCENDING), ("run_at", DESCENDING)], "experiment_run",
              "Latest results per experiment for the Performance page."),
]

ALL_INDEXES = POST_INDEXES + AUX_INDEXES


def ensure_indexes(db: Database | None = None, include_text: bool = True, only: str | None = None) -> list[str]:
    """Create indexes (idempotent). Returns the names created/confirmed."""
    db = db if db is not None else mongo.get_db()
    created = []
    for spec in ALL_INDEXES:
        if only and spec.collection != only:
            continue
        if not include_text and spec.name == "text_search":
            continue
        db[spec.collection].create_index(spec.keys, name=spec.name, **spec.options)
        created.append(f"{spec.collection}.{spec.name}")
    return created


def drop_secondary_indexes(db: Database, collection: str = mongo.POSTS, keep: tuple[str, ...] = ("uniq_post_id",)) -> None:
    """Drop every index except `_id_` and the ones in `keep` (used by experiments)."""
    for name in list(db[collection].index_information()):
        if name != "_id_" and name not in keep:
            db[collection].drop_index(name)


def index_documentation() -> list[dict]:
    return [
        {"collection": s.collection, "name": s.name, "keys": [[k, v] for k, v in s.keys],
         "options": s.options, "reason": s.reason}
        for s in ALL_INDEXES
    ]
