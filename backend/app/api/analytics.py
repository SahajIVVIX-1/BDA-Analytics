"""Dashboard and analytics endpoints (read-only)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.analytics import anomalies, queries
from app.analytics.source import Filters, filters_dependency
from app.database.mongo import get_db
from app.services import cache

router = APIRouter(prefix="/api", tags=["analytics"])

TTL = 120  # seconds; cache is cleared after every ingestion job

Granularity = Literal["hour", "day", "week", "month"]
FiltersQ = Annotated[Filters, Depends(filters_dependency)]


def _key(name: str, f: Filters | None = None, **kw) -> str:
    parts = [name, f.model_dump_json() if f else ""] + [f"{k}={v}" for k, v in sorted(kw.items())]
    return "|".join(parts)


def db_dep():
    return get_db()


@router.get("/dashboard/overview", summary="KPI cards for the overview page")
def overview(f: FiltersQ, db=Depends(db_dep)):
    return cache.cached(_key("overview", f), TTL, lambda: queries.overview(db, f))


@router.get("/meta/filters", summary="Values for filter dropdowns and the dataset date range")
def filter_options(db=Depends(db_dep)):
    return cache.cached("filters", TTL, lambda: queries.filter_options(db))


@router.get("/analytics/timeseries", summary="Posts / reach / engagement per time bucket")
def timeseries(f: FiltersQ, granularity: Granularity = "day",
               split_by: Literal["sentiment", "topic", "language", "country"] | None = None, db=Depends(db_dep)):
    return cache.cached(_key("ts", f, g=granularity, s=split_by), TTL,
                        lambda: queries.timeseries(db, f, granularity, split_by))


@router.get("/analytics/activity", summary="Posting activity heatmap (day of week x hour, UTC)")
def activity(f: FiltersQ, db=Depends(db_dep)):
    return cache.cached(_key("activity", f), TTL, lambda: queries.hourly_profile(db, f))


@router.get("/analytics/sentiment", summary="Sentiment distribution, over time and by topic/language/country")
def sentiment(f: FiltersQ, granularity: Granularity = "week", db=Depends(db_dep)):
    return cache.cached(_key("sentiment", f, g=granularity), TTL, lambda: queries.sentiment(db, f, granularity))


@router.get("/analytics/topics", summary="Topic distribution, timeline, sentiment, engagement and growth")
def topics(f: FiltersQ, granularity: Granularity = "week", top: int = Query(8, ge=1, le=30), db=Depends(db_dep)):
    return cache.cached(_key("topics", f, g=granularity, top=top), TTL,
                        lambda: queries.topics(db, f, granularity, top))


@router.get("/analytics/trends", summary="Trending hashtags / keywords / topics (window-over-window)")
def trends(kind: Literal["hashtag", "keyword", "topic"] = "hashtag", end: date | None = None,
           window_days: int = Query(7, ge=1, le=180), limit: int = Query(25, ge=1, le=200),
           min_count: int = Query(20, ge=1), language: str | None = None, timeline: bool = True,
           db=Depends(db_dep)):
    def run():
        res = queries.trends(db, kind=kind, end=end, window_days=window_days, limit=limit, min_count=min_count,
                             language=language)
        if timeline and res["items"] and res["window"]:
            # Daily timeline for the top items over 4x the comparison span (context before the trend).
            end_day = res["window"]["current"][1].date() - timedelta(days=1)
            start_day = end_day - timedelta(days=window_days * 8 - 1)
            keys = [i["key"] for i in res["items"][:8]]
            res["timeline"] = queries.trend_timeline(db, kind, keys, start_day, end_day)
        return res
    return cache.cached(_key("trends", None, k=kind, e=end, w=window_days, l=limit, m=min_count, lang=language,
                             t=timeline), TTL, run)


@router.get("/analytics/hashtags", summary="Most used hashtags")
def hashtags(f: FiltersQ, limit: int = Query(30, ge=1, le=200), db=Depends(db_dep)):
    return cache.cached(_key("hashtags", f, l=limit), TTL, lambda: queries.top_hashtags(db, f, limit))


@router.get("/analytics/engagement", summary="Engagement totals, over time, by sentiment/topic, top posts")
def engagement(f: FiltersQ, granularity: Granularity = "week", top: int = Query(10, ge=1, le=50),
               db=Depends(db_dep)):
    return cache.cached(_key("engagement", f, g=granularity, top=top), TTL,
                        lambda: queries.engagement(db, f, granularity, top))


@router.get("/analytics/geography", summary="Posts, sentiment and topics by country")
def geography(f: FiltersQ, db=Depends(db_dep)):
    return cache.cached(_key("geo", f), TTL, lambda: queries.geography(db, f))


@router.get("/analytics/languages", summary="Posts, sentiment and topics by language")
def languages(f: FiltersQ, db=Depends(db_dep)):
    return cache.cached(_key("lang", f), TTL, lambda: queries.languages(db, f))


@router.get("/analytics/anomalies", summary="Volume / sentiment anomalies (rolling z-score, IQR, Isolation Forest)")
def detect_anomalies(f: FiltersQ, z: float = Query(3.0, ge=1.0, le=10.0),
                     contamination: float = Query(0.02, gt=0, le=0.2),
                     min_volume: int = Query(100, ge=0, le=100_000, description="z-score rules ignore smaller days"),
                     db=Depends(db_dep)):
    return cache.cached(_key("anom", f, z=z, c=contamination, mv=min_volume), TTL,
                        lambda: anomalies.detect(db, f, z, contamination, min_volume=min_volume))


@router.get("/analytics/users", summary="Most active accounts and behaviour by account category")
def users(limit: int = Query(20, ge=1, le=100), category: str | None = None, db=Depends(db_dep)):
    return cache.cached(_key("users", None, l=limit, c=category), TTL, lambda: queries.users(db, limit, category))
