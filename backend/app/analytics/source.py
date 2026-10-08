"""Query planning: decide whether a request can be answered from the pre-aggregated
`daily_cube` or must run live against `posts`, and expose field expressions so the
same pipeline code works on both.

The cube holds one row per (day, language, country, sentiment, topic) so any
filter on those dimensions (plus a date range) can be answered from it. Filters
on anything else (hashtag, free text, engagement threshold, retweets) need the
raw posts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel, Field, field_validator

from app.database import mongo

SENTIMENTS = ("positive", "neutral", "negative")
GRANULARITIES = ("hour", "day", "week", "month")


class Filters(BaseModel):
    start: date | None = None
    end: date | None = None  # inclusive
    language: str | None = None
    country: str | None = None
    sentiment: str | None = Field(default=None, pattern="^(positive|neutral|negative|not_analyzed)$")
    topic: str | None = None
    hashtag: str | None = None
    q: str | None = Field(default=None, max_length=200)
    min_engagement: int | None = Field(default=None, ge=0)
    exclude_retweets: bool = False
    user: str | None = Field(default=None, max_length=50)
    mode: str = Field(default="auto", pattern="^(auto|live|cube)$")

    @field_validator("hashtag")
    @classmethod
    def _strip_hash(cls, v):
        return v.lstrip("#").lower().strip() or None if v else None

    @property
    def needs_live(self) -> bool:
        return bool(self.hashtag or self.q or self.user or self.min_engagement is not None or self.exclude_retweets)

    def date_range(self) -> tuple[datetime | None, datetime | None]:
        s = datetime.combine(self.start, time.min, tzinfo=UTC) if self.start else None
        e = datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=UTC) if self.end else None
        return s, e


@dataclass
class Source:
    """Field expressions for one of the two data sources."""
    name: str
    collection: str
    date: str
    language: str
    country: str
    sentiment: str
    topic: str
    count: object
    reach: str
    engagement: str
    likes: str
    comments: str
    shares: str
    score_sum: object
    retweets: object

    def match(self, f: Filters) -> dict:
        m: dict = {}
        s, e = f.date_range()
        if s or e:
            m[self.date[1:]] = {k: v for k, v in (("$gte", s), ("$lt", e)) if v}
        if self.name == "cube":
            if f.language:
                m["language"] = f.language
            if f.country:
                m["country"] = f.country
            if f.sentiment:
                m["sentiment"] = f.sentiment
            if f.topic:
                m["topic_id"] = f.topic
            return m
        if f.language:
            m["language"] = None if f.language == "unknown" else f.language
        if f.country:
            m["location.country"] = None if f.country == "Unknown" else f.country
        if f.sentiment:
            m["sentiment.label"] = None if f.sentiment == "not_analyzed" else f.sentiment
        if f.topic:
            m["topic.id"] = None if f.topic == "none" else f.topic
        if f.hashtag:
            m["hashtags"] = f.hashtag
        if f.q:
            m["$text"] = {"$search": f.q}
        if f.min_engagement is not None:
            m["engagement.total"] = {"$gte": f.min_engagement}
        if f.exclude_retweets:
            m["is_retweet"] = False
        if f.user:
            m["user.username"] = f.user
        return m


CUBE = Source(
    name="cube", collection=mongo.DAILY_CUBE, date="$day", language="$language", country="$country",
    sentiment="$sentiment", topic="$topic_id", count="$posts", reach="$reach", engagement="$engagement",
    likes="$likes", comments="$comments", shares="$shares", score_sum="$score_sum", retweets="$retweets",
)
POSTS = Source(
    name="posts", collection=mongo.POSTS, date="$created_at",
    language={"$ifNull": ["$language", "unknown"]},  # type: ignore[arg-type]
    country={"$ifNull": ["$location.country", "Unknown"]},  # type: ignore[arg-type]
    sentiment={"$ifNull": ["$sentiment.label", "not_analyzed"]},  # type: ignore[arg-type]
    topic={"$ifNull": ["$topic.id", "none"]},  # type: ignore[arg-type]
    count=1, reach="$reach", engagement="$engagement.total", likes="$engagement.likes",
    comments="$engagement.comments", shares="$engagement.shares",
    score_sum={"$ifNull": ["$sentiment.score", 0]}, retweets={"$cond": ["$is_retweet", 1, 0]},
)


def choose_source(f: Filters, granularity: str = "day") -> Source:
    if f.mode == "live" or f.needs_live or granularity == "hour":
        return POSTS
    if f.mode == "cube":
        return CUBE
    return CUBE


def sum_(expr) -> dict:
    return {"$sum": {"$ifNull": [expr, 0]} if isinstance(expr, str) else expr}


def bucket(src: Source, granularity: str) -> dict:
    if granularity not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}")
    if granularity == "week":
        return {"$dateTrunc": {"date": src.date, "unit": "week", "startOfWeek": "monday"}}
    return {"$dateTrunc": {"date": src.date, "unit": granularity}}


def filters_dependency(
    start: date | None = None,
    end: date | None = None,
    language: str | None = None,
    country: str | None = None,
    sentiment: str | None = None,
    topic: str | None = None,
    hashtag: str | None = None,
    q: str | None = None,
    min_engagement: int | None = None,
    exclude_retweets: bool = False,
    user: str | None = None,
    mode: str = "auto",
) -> Filters:
    """FastAPI dependency: builds a validated Filters object from query parameters."""
    from fastapi.exceptions import RequestValidationError
    from pydantic import ValidationError

    try:
        return Filters(start=start, end=end, language=language, country=country, sentiment=sentiment, topic=topic,
                       hashtag=hashtag, q=q, min_engagement=min_engagement, exclude_retweets=exclude_retweets,
                       user=user, mode=mode)
    except ValidationError as e:
        raise RequestValidationError([{**err, "loc": ("query", *err["loc"])} for err in e.errors()]) from e
