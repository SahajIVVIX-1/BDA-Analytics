"""Pre-aggregated ("materialised") analytics collections built with MongoDB pipelines.

Each builder is a single aggregation pipeline, so all the heavy lifting happens
inside MongoDB and nothing comes back to Python. A full rebuild ends each
pipeline with `$out` (bulk-writes a fresh collection, then indexes are built).
An incremental refresh passes the date range of newly ingested posts and ends
with `$merge`, which upserts only the affected (day, ...) rows.

Collections
  daily_cube     one row per (day, language, country, sentiment, topic) with counts and sums.
                 Dashboard charts filtered by those dimensions read this instead of `posts`.
  hourly_cube    one row per (hour, language, sentiment): hourly charts and the activity heatmap.
  hashtag_daily  one row per (day, hashtag): volume, reach, sentiment mix. Feeds trend detection.
  keyword_daily  one row per (day, language, keyword). Feeds keyword trends.
  users          one row per account: activity span, volume, reach, sentiment mix.
"""

from __future__ import annotations

import time
from datetime import datetime

from pymongo.database import Database

from app.database import mongo

DAY = {"$dateTrunc": {"date": "$created_at", "unit": "day"}}


def _range_match(start: datetime | None, end: datetime | None) -> dict:
    if not start and not end:
        return {}
    rng = {}
    if start:
        rng["$gte"] = start
    if end:
        rng["$lt"] = end
    return {"created_at": rng}


def _sentiment_counts(prefix: str = "") -> dict:
    return {
        f"{prefix}positive": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "positive"]}, 1, 0]}},
        f"{prefix}neutral": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "neutral"]}, 1, 0]}},
        f"{prefix}negative": {"$sum": {"$cond": [{"$eq": ["$sentiment.label", "negative"]}, 1, 0]}},
    }


def cube_pipeline(start=None, end=None) -> list[dict]:
    return [
        {"$match": {"processed": True, **_range_match(start, end)}},
        {"$group": {
            "_id": {
                "day": DAY,
                "language": {"$ifNull": ["$language", "unknown"]},
                "country": {"$ifNull": ["$location.country", "Unknown"]},
                "sentiment": {"$ifNull": ["$sentiment.label", "not_analyzed"]},
                "topic_id": {"$ifNull": ["$topic.id", "none"]},
            },
            "posts": {"$sum": 1},
            "retweets": {"$sum": {"$cond": ["$is_retweet", 1, 0]}},
            "with_hashtags": {"$sum": {"$cond": [{"$gt": [{"$size": "$hashtags"}, 0]}, 1, 0]}},
            "reach": {"$sum": {"$ifNull": ["$reach", 0]}},
            "score_sum": {"$sum": {"$ifNull": ["$sentiment.score", 0]}},
            "likes": {"$sum": {"$ifNull": ["$engagement.likes", 0]}},
            "comments": {"$sum": {"$ifNull": ["$engagement.comments", 0]}},
            "shares": {"$sum": {"$ifNull": ["$engagement.shares", 0]}},
            "engagement": {"$sum": {"$ifNull": ["$engagement.total", 0]}},
            "engagement_synthetic": {"$max": {"$ifNull": ["$engagement.synthetic", False]}},
        }},
        {"$project": {
            "_id": 0, "day": "$_id.day", "language": "$_id.language", "country": "$_id.country",
            "sentiment": "$_id.sentiment", "topic_id": "$_id.topic_id", "posts": 1, "retweets": 1,
            "with_hashtags": 1, "reach": 1, "score_sum": 1, "likes": 1, "comments": 1, "shares": 1,
            "engagement": 1, "engagement_synthetic": 1,
        }},
        {"$merge": {"into": mongo.DAILY_CUBE, "on": ["day", "language", "country", "sentiment", "topic_id"],
                    "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def hourly_pipeline(start=None, end=None) -> list[dict]:
    """Posts per (hour, language, sentiment): powers hourly charts and the weekday x hour heatmap."""
    return [
        {"$match": _range_match(start, end)},
        {"$group": {"_id": {"hour": {"$dateTrunc": {"date": "$created_at", "unit": "hour"}},
                            "language": {"$ifNull": ["$language", "unknown"]},
                            "sentiment": {"$ifNull": ["$sentiment.label", "not_analyzed"]}},
                    "posts": {"$sum": 1}, "reach": {"$sum": {"$ifNull": ["$reach", 0]}},
                    "engagement": {"$sum": {"$ifNull": ["$engagement.total", 0]}}}},
        {"$project": {"_id": 0, "hour": "$_id.hour", "language": "$_id.language", "sentiment": "$_id.sentiment",
                      "posts": 1, "reach": 1, "engagement": 1}},
        {"$merge": {"into": mongo.HOURLY_CUBE, "on": ["hour", "language", "sentiment"],
                    "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def hashtag_pipeline(start=None, end=None) -> list[dict]:
    return [
        {"$match": {"hashtags.0": {"$exists": True}, **_range_match(start, end)}},
        {"$project": {"hashtags": 1, "created_at": 1, "reach": 1, "sentiment.label": 1, "engagement.total": 1}},
        {"$unwind": "$hashtags"},
        {"$group": {
            "_id": {"day": DAY, "hashtag": "$hashtags"},
            "posts": {"$sum": 1},
            "reach": {"$sum": {"$ifNull": ["$reach", 0]}},
            "engagement": {"$sum": {"$ifNull": ["$engagement.total", 0]}},
            **_sentiment_counts(),
        }},
        {"$project": {"_id": 0, "day": "$_id.day", "hashtag": "$_id.hashtag", "posts": 1, "reach": 1,
                      "engagement": 1, "positive": 1, "neutral": 1, "negative": 1}},
        {"$merge": {"into": mongo.HASHTAG_DAILY, "on": ["day", "hashtag"],
                    "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def keyword_pipeline(start=None, end=None) -> list[dict]:
    return [
        {"$match": {"processed": True, "keywords.0": {"$exists": True}, **_range_match(start, end)}},
        {"$project": {"keywords": 1, "created_at": 1, "language": 1, "reach": 1}},
        {"$unwind": "$keywords"},
        {"$group": {
            "_id": {"day": DAY, "language": "$language", "keyword": "$keywords"},
            "posts": {"$sum": 1},
            "reach": {"$sum": {"$ifNull": ["$reach", 0]}},
        }},
        {"$project": {"_id": 0, "day": "$_id.day", "language": "$_id.language", "keyword": "$_id.keyword",
                      "posts": 1, "reach": 1}},
        {"$merge": {"into": mongo.KEYWORD_DAILY, "on": ["day", "language", "keyword"],
                    "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def users_pipeline() -> list[dict]:
    return [
        {"$group": {
            "_id": "$user.username",
            "user_id": {"$first": "$user.user_id"},
            "account_category": {"$first": "$user.account_category"},
            "account_type": {"$first": "$user.account_type"},
            "posts": {"$sum": 1},
            "retweets": {"$sum": {"$cond": ["$is_retweet", 1, 0]}},
            "first_post": {"$min": "$created_at"},
            "last_post": {"$max": "$created_at"},
            "max_followers": {"$max": "$user.followers"},
            "avg_followers": {"$avg": "$user.followers"},
            "languages": {"$addToSet": "$language"},
            "hashtag_uses": {"$sum": {"$size": "$hashtags"}},
            **_sentiment_counts(),
        }},
        {"$set": {
            "active_days": {"$add": [1, {"$dateDiff": {"startDate": "$first_post", "endDate": "$last_post",
                                                          "unit": "day"}}]},
            "retweet_ratio": {"$round": [{"$divide": ["$retweets", "$posts"]}, 4]},
            "avg_followers": {"$round": ["$avg_followers", 0]},
        }},
        {"$set": {"posts_per_active_day": {"$round": [{"$divide": ["$posts", "$active_days"]}, 2]}}},
        {"$merge": {"into": mongo.USERS, "on": "_id", "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]


def build_all(db: Database | None = None, start: datetime | None = None, end: datetime | None = None,
              verbose: bool = False) -> dict:
    """Build/refresh every rollup. With a date range, only those days are recomputed."""
    from app.database.indexes import ensure_indexes

    db = db if db is not None else mongo.get_db()
    timings = {}
    if start or end:
        for c in (mongo.DAILY_CUBE, mongo.HOURLY_CUBE, mongo.HASHTAG_DAILY, mongo.KEYWORD_DAILY):
            ensure_indexes(db, only=c)  # $merge needs the unique index on its `on` fields
    jobs = [
        (mongo.DAILY_CUBE, cube_pipeline(start, end)),
        (mongo.HOURLY_CUBE, hourly_pipeline(start, end)),
        (mongo.HASHTAG_DAILY, hashtag_pipeline(start, end)),
        (mongo.KEYWORD_DAILY, keyword_pipeline(start, end)),
        (mongo.USERS, users_pipeline()),
    ]
    full = not start and not end
    for name, pipeline in jobs:
        if full:
            # Full rebuild: $out writes a brand-new collection in bulk, far cheaper than millions of
            # $merge upserts against a unique index. Indexes are then built once on the result.
            pipeline = pipeline[:-1] + [{"$out": name}]
        t = time.perf_counter()
        list(db[mongo.POSTS].aggregate(pipeline, allowDiskUse=True))
        if full:
            ensure_indexes(db, only=name)
        timings[name] = {"seconds": round(time.perf_counter() - t, 2), "documents": db[name].estimated_document_count()}
        if verbose:
            print(f"  {name:<14} {timings[name]['seconds']:>8.1f}s  {timings[name]['documents']:>10,} docs", flush=True)
    return timings
