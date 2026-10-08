"""Map raw records from different sources onto the unified `posts` document.

A *profile* knows the column names of one source. `generic` accepts the most
common field names so arbitrary CSV/JSON uploads work too.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.ingestion import cleaning

PROFILES = ("ira538", "generic")


class InvalidRecord(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _first(rec: dict, *keys):
    """First non-empty value among candidate keys; supports dotted paths for nested JSON."""
    for key in keys:
        cur = rec
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur is not None and cur != "":
            return cur
    return None


def _ira538_fields(rec: dict) -> dict:
    post_type = (rec.get("post_type") or "").strip().upper()
    return {
        "post_id": rec.get("tweet_id"),
        "text": rec.get("content"),
        "created_at": rec.get("publish_date"),
        "language": rec.get("language"),
        "country": rec.get("region"),
        "user": {
            # alt_external_id is the exact account id; external_author_id lost precision in the source CSV.
            "user_id": rec.get("alt_external_id") or rec.get("external_author_id"),
            "username": rec.get("author"),
            "followers": rec.get("followers"),
            "following": rec.get("following"),
            "updates": rec.get("updates"),
            "account_category": rec.get("account_category"),
            "account_type": rec.get("account_type"),
        },
        "post_type": {"RETWEET": "retweet", "QUOTE_TWEET": "quote"}.get(post_type, "original"),
        "is_retweet": str(rec.get("retweet", "")).strip() == "1" or post_type == "RETWEET",
        "engagement": None,  # the source has no likes/comments/shares
    }


def _generic_fields(rec: dict) -> dict:
    likes = _first(rec, "likes", "like_count", "favorite_count", "favorites", "engagement.likes")
    comments = _first(rec, "comments", "comment_count", "reply_count", "replies", "engagement.comments")
    shares = _first(rec, "shares", "share_count", "retweet_count", "retweets", "engagement.shares")
    engagement = None
    if any(v is not None for v in (likes, comments, shares)):
        parts = [cleaning.to_non_negative_int(v) or 0 for v in (likes, comments, shares)]
        engagement = {"likes": parts[0], "comments": parts[1], "shares": parts[2], "total": sum(parts),
                      "synthetic": bool(_first(rec, "engagement.synthetic") or False)}
    is_rt = _first(rec, "is_retweet", "retweet")
    return {
        "post_id": _first(rec, "post_id", "id", "tweet_id", "id_str", "status_id"),
        "text": _first(rec, "text", "content", "full_text", "body", "message", "tweet"),
        "created_at": _first(rec, "created_at", "timestamp", "date", "publish_date", "time", "datetime"),
        "language": _first(rec, "language", "lang"),
        "country": _first(rec, "location.country", "country", "region", "user_location", "place.country"),
        "city": _first(rec, "location.city", "city"),
        "user": {
            "user_id": _first(rec, "user.user_id", "user.id", "user_id", "author_id"),
            "username": _first(rec, "user.username", "user.screen_name", "username", "screen_name", "user", "author"),
            "followers": _first(rec, "user.followers", "user.followers_count", "followers", "followers_count"),
            "following": _first(rec, "user.following", "following", "friends_count"),
            "updates": None,
            "account_category": None,
            "account_type": None,
        },
        "post_type": "retweet" if str(is_rt).lower() in ("1", "true") else "original",
        "is_retweet": str(is_rt).lower() in ("1", "true"),
        "engagement": engagement,
        "hashtags_field": _first(rec, "hashtags"),
    }


def normalize_record(rec: dict, profile: str, source: str, job_id: str | None = None,
                     now: datetime | None = None) -> dict:
    """Return a `posts` document or raise InvalidRecord(reason)."""
    if "__parse_error__" in rec:
        raise InvalidRecord("parse_error")
    f = _ira538_fields(rec) if profile == "ira538" else _generic_fields(rec)

    post_id = f["post_id"]
    if post_id is None or str(post_id).strip() == "":
        raise InvalidRecord("missing_id")
    raw_text = f["text"]
    if raw_text is None or not str(raw_text).strip():
        raise InvalidRecord("empty_text")
    created_at = cleaning.parse_timestamp(f["created_at"], now=now)
    if created_at is None:
        raise InvalidRecord("invalid_timestamp")

    raw_text = str(raw_text)
    c = cleaning.clean_text(raw_text)
    hashtags = c["hashtags"]
    extra_tags = f.get("hashtags_field")
    if isinstance(extra_tags, list):  # JSON sources may already carry a hashtag array
        for t in extra_tags:
            t = str(t).lstrip("#").lower().strip()
            if t and t not in hashtags:
                hashtags.append(t)

    u = f["user"]
    username = str(u["username"]).strip() if u.get("username") not in (None, "") else "unknown"
    user = {
        "user_id": str(u["user_id"]).strip() if u.get("user_id") not in (None, "") else None,
        "username": username,
        "followers": cleaning.to_non_negative_int(u.get("followers")),
        "following": cleaning.to_non_negative_int(u.get("following")),
        "updates": cleaning.to_non_negative_int(u.get("updates")),
    }
    if u.get("account_category"):
        user["account_category"] = str(u["account_category"])
    if u.get("account_type"):
        user["account_type"] = str(u["account_type"])

    country = cleaning.normalize_location(f.get("country"))
    city = cleaning.normalize_location(f.get("city"))
    location = {"country": country, "city": city} if (country or city) else None

    flags = cleaning.quality_flags(c["clean_text"], hashtags, c["mentions"], c["url_count"])
    if not c["clean_text"]:
        flags.append("no_text_content")

    doc = {
        "post_id": str(post_id).strip(),
        "source": source,
        "user": user,
        "text": raw_text,
        "clean_text": c["clean_text"],
        "created_at": created_at,
        "language": cleaning.normalize_language(f.get("language")),
        "location": location,
        "hashtags": hashtags,
        "mentions": c["mentions"],
        "url_count": c["url_count"],
        "emojis": c["emojis"],
        "post_type": f["post_type"],
        "is_retweet": bool(f["is_retweet"] or c["rt_prefix"]),
        "reach": user["followers"],
        "engagement": f["engagement"],
        "sentiment": None,
        "topic": None,
        "keywords": [],
        "text_hash": cleaning.text_fingerprint(c["clean_text"]),
        "quality_flags": flags,
        "processed": False,
        "ingested_at": now or datetime.now(UTC),
        "ingestion_job_id": job_id,
    }
    return doc
