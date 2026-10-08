"""Analytics queries. Every statistic is computed inside MongoDB with an aggregation
pipeline; Python only reshapes the (small) results for the API.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from pymongo.database import Database

from app.analytics.source import CUBE, POSTS, SENTIMENTS, Filters, Source, bucket, choose_source, sum_
from app.database import mongo
from app.services import cache

MIN_SHARE_N = 100  # minimum analysed posts in a period before sentiment shares are plotted
NON_TOPICS = [None, "none", "en-other", "ru-other"]


def _agg(db: Database, src: Source, pipeline: list[dict]) -> list[dict]:
    return list(db[src.collection].aggregate(pipeline, allowDiskUse=True))


def _meta(src: Source, t0: float) -> dict:
    return {"source": src.name, "query_ms": round((time.perf_counter() - t0) * 1000, 1)}


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _sentiment_block(counts: dict[str, int]) -> dict:
    analysed = sum(counts.get(s, 0) for s in SENTIMENTS)
    return {
        "counts": {s: counts.get(s, 0) for s in (*SENTIMENTS, "not_analyzed")},
        "analysed": analysed,
        "percent": {s: _pct(counts.get(s, 0), analysed) for s in SENTIMENTS},
    }


def engagement_is_synthetic(db: Database) -> bool:
    return db[mongo.POSTS].find_one({"engagement.synthetic": True}, {"_id": 1}) is not None


def topic_labels(db: Database) -> dict[str, dict]:
    return {t["_id"]: {"label": t["label"], "language": t["language"], "top_terms": t.get("top_terms", [])[:8]}
            for t in db[mongo.TOPICS].find()}


# --------------------------------------------------------------------------- overview

def dataset_bounds(db: Database) -> dict:
    return cache.cached(f"bounds:{db.name}", 600, lambda: _dataset_bounds(db))


def _dataset_bounds(db: Database) -> dict:
    first = db[mongo.POSTS].find_one({}, {"created_at": 1}, sort=[("created_at", 1)])
    last = db[mongo.POSTS].find_one({}, {"created_at": 1}, sort=[("created_at", -1)])
    return {"first": first and first["created_at"], "last": last and last["created_at"],
            "active_end": active_end(db)}


def active_end(db: Database, quantile: float = 0.99):
    return cache.cached(f"active_end:{db.name}:{quantile}", 600, lambda: _active_end(db, quantile))


def _active_end(db: Database, quantile: float = 0.99):
    """Day by which `quantile` of all posts were published (end of the main activity period).

    Used as the default end of trend windows: the last calendar days of a dataset often hold a
    sparse tail (here: a few thousand posts in 2018), where window-over-window growth is meaningless.
    """
    rows = list(db[mongo.DAILY_CUBE].aggregate([
        {"$group": {"_id": "$day", "n": {"$sum": "$posts"}}},
        {"$setWindowFields": {"sortBy": {"_id": 1}, "output": {
            "cum": {"$sum": "$n", "window": {"documents": ["unbounded", "current"]}}}}},
        {"$group": {"_id": None, "days": {"$push": {"d": "$_id", "cum": "$cum"}}, "total": {"$sum": "$n"}}},
        {"$project": {"day": {"$first": {"$filter": {"input": "$days", "cond": {
            "$gte": ["$$this.cum", {"$multiply": ["$total", quantile]}]}}}}}},
    ]))
    return rows[0]["day"]["d"] if rows and rows[0].get("day") else None


def overview(db: Database, f: Filters) -> dict:
    t0 = time.perf_counter()
    src = choose_source(f)
    match = src.match(f)
    facet = {
        "totals": [{"$group": {"_id": None, "posts": sum_(src.count), "reach": sum_(src.reach),
                               "retweets": sum_(src.retweets), "engagement": sum_(src.engagement),
                               "likes": sum_(src.likes), "comments": sum_(src.comments), "shares": sum_(src.shares),
                               "score_sum": sum_(src.score_sum)}}],
        "sentiment": [{"$group": {"_id": src.sentiment, "n": sum_(src.count)}}],
        "topics": [{"$match": {(src.topic[1:] if isinstance(src.topic, str) else "topic.id"): {"$nin": NON_TOPICS}}},
                   {"$group": {"_id": src.topic}}, {"$count": "n"}],
        "languages": [{"$group": {"_id": src.language}}, {"$count": "n"}],
        "countries": [{"$group": {"_id": src.country}}, {"$count": "n"}],
        "range": [{"$group": {"_id": None, "first": {"$min": src.date}, "last": {"$max": src.date}}}],
    }
    res = _agg(db, src, [{"$match": match}, {"$facet": facet}])[0]
    tot = res["totals"][0] if res["totals"] else {}
    sent = _sentiment_block({r["_id"]: r["n"] for r in res["sentiment"]})
    posts = tot.get("posts", 0)
    out = {
        "total_posts": posts,
        "sentiment": sent,
        "avg_sentiment_score": round(tot.get("score_sum", 0) / sent["analysed"], 4) if sent["analysed"] else None,
        "total_reach": tot.get("reach", 0),
        "retweet_share": _pct(tot.get("retweets", 0), posts),
        "engagement": {"total": tot.get("engagement", 0), "likes": tot.get("likes", 0),
                       "comments": tot.get("comments", 0), "shares": tot.get("shares", 0),
                       "synthetic": engagement_is_synthetic(db)},
        "topics": res["topics"][0]["n"] if res["topics"] else 0,
        "languages": res["languages"][0]["n"] if res["languages"] else 0,
        "countries": res["countries"][0]["n"] if res["countries"] else 0,
        "date_range": res["range"][0] if res["range"] else None,
    }
    out["users"] = db[mongo.USERS].estimated_document_count()
    trend = trends(db, kind="hashtag", end=f.end, window_days=7, limit=1000, min_count=10)
    out["trending_hashtags"] = sum(1 for t in trend["items"] if t["growth_pct"] > 0)
    out["meta"] = _meta(src, t0)
    return out


# --------------------------------------------------------------------------- time series

def timeseries(db: Database, f: Filters, granularity: str = "day", split_by: str | None = None) -> dict:
    """Posts (and reach/engagement) per time bucket, optionally split by sentiment/topic/language."""
    t0 = time.perf_counter()
    src = choose_source(f, granularity)
    key: dict = {"t": bucket(src, granularity)}
    if split_by:
        key["s"] = {"sentiment": src.sentiment, "topic": src.topic, "language": src.language,
                    "country": src.country}[split_by]
    rows = _agg(db, src, [
        {"$match": src.match(f)},
        {"$group": {"_id": key, "posts": sum_(src.count), "reach": sum_(src.reach),
                    "engagement": sum_(src.engagement), "score_sum": sum_(src.score_sum)}},
        {"$sort": {"_id.t": 1}},
    ])
    if not split_by:
        series = [{"t": r["_id"]["t"], "posts": r["posts"], "reach": r["reach"], "engagement": r["engagement"]}
                  for r in rows]
        return {"granularity": granularity, "series": series, "meta": _meta(src, t0)}
    points: dict = {}
    for r in rows:
        p = points.setdefault(r["_id"]["t"], {"t": r["_id"]["t"]})
        p[str(r["_id"]["s"])] = r["posts"]
    return {"granularity": granularity, "split_by": split_by, "series": list(points.values()),
            "keys": sorted({str(r["_id"]["s"]) for r in rows}), "meta": _meta(src, t0)}


def _hourly_ok(f: Filters) -> bool:
    return f.mode != "live" and not (f.needs_live or f.country or f.topic)


def hourly_profile(db: Database, f: Filters) -> dict:
    """Posting activity by day of week x hour of day (UTC).

    Answered from `hourly_cube` when the filters allow it (date / language / sentiment), otherwise live
    from `posts` with $isoDayOfWeek / $hour on the raw timestamps.
    """
    t0 = time.perf_counter()
    if _hourly_ok(f):
        s, e = f.date_range()
        m: dict = {}
        if s or e:
            m["hour"] = {k: v for k, v in (("$gte", s), ("$lt", e)) if v}
        if f.language:
            m["language"] = f.language
        if f.sentiment:
            m["sentiment"] = f.sentiment
        coll, date_field, count = mongo.HOURLY_CUBE, "$hour", "$posts"
        src_name = mongo.HOURLY_CUBE
    else:
        m, coll, date_field, count, src_name = POSTS.match(f), mongo.POSTS, "$created_at", 1, "posts"
    rows = list(db[coll].aggregate([
        {"$match": m},
        {"$group": {"_id": {"dow": {"$isoDayOfWeek": date_field}, "hour": {"$hour": date_field}},
                    "posts": {"$sum": count}}},
        {"$sort": {"_id.dow": 1, "_id.hour": 1}},
    ], allowDiskUse=True))
    return {"cells": [{"dow": r["_id"]["dow"], "hour": r["_id"]["hour"], "posts": r["posts"]} for r in rows],
            "timezone": "UTC", "meta": {"source": src_name, "query_ms": round((time.perf_counter() - t0) * 1000, 1)}}


# --------------------------------------------------------------------------- sentiment

def sentiment(db: Database, f: Filters, granularity: str = "day") -> dict:
    t0 = time.perf_counter()
    src = choose_source(f, granularity)
    labels = topic_labels(db)
    facet = {
        "dist": [{"$group": {"_id": src.sentiment, "n": sum_(src.count), "score": sum_(src.score_sum)}}],
        "over_time": [{"$group": {"_id": {"t": bucket(src, granularity), "s": src.sentiment}, "n": sum_(src.count),
                                  "score": sum_(src.score_sum)}}, {"$sort": {"_id.t": 1}}],
        "by_topic": [{"$group": {"_id": {"k": src.topic, "s": src.sentiment}, "n": sum_(src.count)}}],
        "by_language": [{"$group": {"_id": {"k": src.language, "s": src.sentiment}, "n": sum_(src.count)}}],
        "by_country": [{"$group": {"_id": {"k": src.country, "s": src.sentiment}, "n": sum_(src.count)}}],
    }
    res = _agg(db, src, [{"$match": src.match(f)}, {"$facet": facet}])[0]

    dist = _sentiment_block({r["_id"]: r["n"] for r in res["dist"]})
    score_total = sum(r["score"] for r in res["dist"])

    series: dict = {}
    for r in res["over_time"]:
        p = series.setdefault(r["_id"]["t"], {"t": r["_id"]["t"], "positive": 0, "neutral": 0, "negative": 0,
                                               "score_sum": 0.0})
        if r["_id"]["s"] in SENTIMENTS:
            p[r["_id"]["s"]] = r["n"]
            p["score_sum"] += r["score"]
    over_time = []
    for p in series.values():
        n = p["positive"] + p["neutral"] + p["negative"]
        if not n:
            continue
        # Shares from a handful of posts swing 0-100%; below MIN_SHARE_N they are reported as null.
        ok = n >= MIN_SHARE_N
        over_time.append({"t": p["t"], "analysed": n, "reliable": ok,
                          "positive": p["positive"], "neutral": p["neutral"], "negative": p["negative"],
                          "avg_score": round(p.pop("score_sum") / n, 4),
                          "positive_pct": _pct(p["positive"], n) if ok else None,
                          "negative_pct": _pct(p["negative"], n) if ok else None})

    def breakdown(rows, label_fn=lambda k: k, min_analysed=1):
        acc: dict = {}
        for r in rows:
            a = acc.setdefault(r["_id"]["k"], {"key": r["_id"]["k"], "positive": 0, "neutral": 0, "negative": 0,
                                                "not_analyzed": 0})
            a[r["_id"]["s"]] = a.get(r["_id"]["s"], 0) + r["n"]
        out = []
        for a in acc.values():
            n = a["positive"] + a["neutral"] + a["negative"]
            if n < min_analysed:
                continue
            out.append({**a, "label": label_fn(a["key"]), "analysed": n,
                        **{f"{s}_pct": _pct(a[s], n) for s in SENTIMENTS},
                        "net_sentiment": round((a["positive"] - a["negative"]) / n, 4)})
        return sorted(out, key=lambda x: -x["analysed"])

    return {
        "distribution": dist,
        "avg_score": round(score_total / dist["analysed"], 4) if dist["analysed"] else None,
        "over_time": over_time,
        "by_topic": breakdown(res["by_topic"], lambda k: labels.get(k, {}).get("label", k), 1)[:30],
        "by_language": breakdown(res["by_language"])[:20],
        "by_country": breakdown(res["by_country"], min_analysed=100)[:30],
        "granularity": granularity,
        "note": "Sentiment is computed for English posts only; other languages are counted as not_analyzed.",
        "meta": _meta(src, t0),
    }


# --------------------------------------------------------------------------- topics

def topics(db: Database, f: Filters, granularity: str = "week", top: int = 8) -> dict:
    t0 = time.perf_counter()
    src = choose_source(f, granularity)
    labels = topic_labels(db)
    match = src.match(f)
    topic_field = "topic_id" if src is CUBE else "topic.id"
    match.setdefault(topic_field, {"$nin": [None, "none"]})
    facet = {
        "dist": [{"$group": {"_id": src.topic, "posts": sum_(src.count), "reach": sum_(src.reach),
                             "engagement": sum_(src.engagement), "score_sum": sum_(src.score_sum),
                             **{s: sum_({"$cond": [{"$eq": [src.sentiment, s]}, src.count, 0]}) for s in SENTIMENTS}}},
                 {"$sort": {"posts": -1}}],
        "timeline": [{"$group": {"_id": {"t": bucket(src, granularity), "k": src.topic}, "n": sum_(src.count)}},
                     {"$sort": {"_id.t": 1}}],
    }
    res = _agg(db, src, [{"$match": match}, {"$facet": facet}])[0]
    total = sum(r["posts"] for r in res["dist"]) or 1
    dist = []
    for r in res["dist"]:
        analysed = r["positive"] + r["neutral"] + r["negative"]
        meta = labels.get(r["_id"], {})
        dist.append({"topic_id": r["_id"], "label": meta.get("label", r["_id"]), "language": meta.get("language"),
                     "top_terms": meta.get("top_terms", []), "posts": r["posts"], "share_pct": _pct(r["posts"], total),
                     "reach": r["reach"], "engagement": r["engagement"],
                     "avg_engagement": round(r["engagement"] / r["posts"], 2) if r["posts"] else 0,
                     "sentiment": {s: r[s] for s in SENTIMENTS},
                     "net_sentiment": round((r["positive"] - r["negative"]) / analysed, 4) if analysed else None,
                     "avg_score": round(r["score_sum"] / analysed, 4) if analysed else None})
    top_ids = [d["topic_id"] for d in dist if not d["topic_id"].endswith("-other")][:top]
    points: dict = {}
    for r in res["timeline"]:
        if r["_id"]["k"] in top_ids:
            points.setdefault(r["_id"]["t"], {"t": r["_id"]["t"]})[r["_id"]["k"]] = r["n"]
    growth = trends(db, kind="topic", end=f.end, window_days=30, limit=100, min_count=1, language=f.language)
    gmap = {g["key"]: g for g in growth["items"]}
    for d in dist:
        g = gmap.get(d["topic_id"])
        d["growth_pct"] = g["growth_pct"] if g else None
        d["share_growth_pct"] = g.get("share_growth_pct") if g else None
    return {"topics": dist, "growth_window": growth.get("window"), "growth_warning": growth.get("warning"),
            "timeline": list(points.values()), "timeline_keys": top_ids,
            "labels": {k: v["label"] for k, v in labels.items()}, "granularity": granularity,
            "method": "TF-IDF + NMF per language (en, ru); see docs/methodology.md", "meta": _meta(src, t0)}


# --------------------------------------------------------------------------- trends

def trends(db: Database, kind: str = "hashtag", end=None, window_days: int = 7, limit: int = 25,
           min_count: int = 20, language: str | None = None, smoothing: float = 5.0) -> dict:
    """Window-over-window trend detection, computed entirely in an aggregation pipeline.

    current  = mentions in (end - window, end]        previous = mentions in (end - 2*window, end - window]
    growth_pct  = (current - previous) / max(previous, 1) * 100
    trend_score = log10(1 + current) * log2((current + a) / (previous + a)) * (1 + 0.1 * log10(1 + avg_reach))
    with additive smoothing a = 5 so that a jump from 0 to 3 mentions does not count as "infinite" growth.
    Only items with current >= min_count are ranked.
    """
    t0 = time.perf_counter()
    if end is None:
        last = active_end(db) or dataset_bounds(db)["last"]
        if last is None:
            return {"kind": kind, "items": [], "window": None}
        end_dt = datetime(last.year, last.month, last.day, tzinfo=UTC) + timedelta(days=1)
    else:
        end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
    cur_start = end_dt - timedelta(days=window_days)
    prev_start = cur_start - timedelta(days=window_days)

    if kind == "hashtag":
        coll, key_field, count_field, match = mongo.HASHTAG_DAILY, "$hashtag", "$posts", {}
    elif kind == "keyword":
        coll, key_field, count_field, match = mongo.KEYWORD_DAILY, "$keyword", "$posts", {}
        if language:
            match["language"] = language
    elif kind == "topic":
        coll, key_field, count_field = mongo.DAILY_CUBE, "$topic_id", "$posts"
        match = {"topic_id": {"$nin": ["none"]}}
        if language:
            match["language"] = language
    else:
        raise ValueError("kind must be hashtag, keyword or topic")

    a = float(smoothing)
    pipeline = [
        {"$match": {"day": {"$gte": prev_start, "$lt": end_dt}, **match}},
        {"$group": {
            "_id": key_field,
            "current": {"$sum": {"$cond": [{"$gte": ["$day", cur_start]}, count_field, 0]}},
            "previous": {"$sum": {"$cond": [{"$lt": ["$day", cur_start]}, count_field, 0]}},
            "reach": {"$sum": {"$cond": [{"$gte": ["$day", cur_start]}, "$reach", 0]}},
        }},
        {"$match": {"current": {"$gte": min_count}}},
        {"$set": {
            "growth_pct": {"$round": [{"$multiply": [100, {"$divide": [{"$subtract": ["$current", "$previous"]},
                                                                        {"$max": ["$previous", 1]}]}]}, 1]},
            "avg_reach": {"$divide": ["$reach", "$current"]},
        }},
        {"$set": {"trend_score": {"$round": [{"$multiply": [
            {"$log10": {"$add": [1, "$current"]}},
            {"$log": [{"$divide": [{"$add": ["$current", a]}, {"$add": ["$previous", a]}]}, 2]},
            {"$add": [1, {"$multiply": [0.1, {"$log10": {"$add": [1, "$avg_reach"]}}]}]},
        ]}, 3]}}},
        {"$sort": {"trend_score": -1}},
        {"$limit": limit},
    ]
    rows = list(db[coll].aggregate(pipeline, allowDiskUse=True))
    labels = topic_labels(db) if kind == "topic" else {}

    # Total posts per window. If the whole dataset is much busier in one window (e.g. a collection gap),
    # raw growth mostly reflects volume; share growth (change in the item's share of all posts) corrects for it.
    tot = list(db[mongo.DAILY_CUBE].aggregate([
        {"$match": {"day": {"$gte": prev_start, "$lt": end_dt}}},
        {"$group": {"_id": None,
                    "current": {"$sum": {"$cond": [{"$gte": ["$day", cur_start]}, "$posts", 0]}},
                    "previous": {"$sum": {"$cond": [{"$lt": ["$day", cur_start]}, "$posts", 0]}}}}]))
    totals = {"current": tot[0]["current"], "previous": tot[0]["previous"]} if tot else {"current": 0, "previous": 0}
    ratio = totals["current"] / totals["previous"] if totals["previous"] else None
    warning = None
    if ratio is None or ratio > 3 or ratio < 1 / 3:
        warning = (f"Overall volume differs strongly between the windows ({totals['current']:,} vs {totals['previous']:,} posts), "
                   "for example because of a gap in data collection. Raw growth mostly reflects that; use share growth.")

    def share_growth(cur, prev):
        if not totals["current"] or not totals["previous"]:
            return None
        s_cur = cur / totals["current"]
        s_prev = max(prev, 1) / totals["previous"]
        return round(100 * (s_cur / s_prev - 1), 1)

    items = [{"key": r["_id"], "label": labels.get(r["_id"], {}).get("label", r["_id"]) if kind == "topic" else r["_id"],
              "current": r["current"], "previous": r["previous"], "growth_pct": r["growth_pct"],
              "share_growth_pct": share_growth(r["current"], r["previous"]),
              "avg_reach": round(r["avg_reach"]), "trend_score": r["trend_score"]} for r in rows]
    return {"kind": kind, "window_days": window_days,
            "window": {"current": [cur_start, end_dt], "previous": [prev_start, cur_start]},
            "totals": totals, "warning": warning,
            "items": items, "formula": "log10(1+current) * log2((current+5)/(previous+5)) * (1+0.1*log10(1+avg_reach))",
            "meta": {"source": coll, "query_ms": round((time.perf_counter() - t0) * 1000, 1)}}


def trend_timeline(db: Database, kind: str, keys: list[str], start=None, end=None) -> dict:
    coll, field = {"hashtag": (mongo.HASHTAG_DAILY, "hashtag"), "keyword": (mongo.KEYWORD_DAILY, "keyword"),
                   "topic": (mongo.DAILY_CUBE, "topic_id")}[kind]
    m: dict = {field: {"$in": keys}}
    if start or end:
        m["day"] = {}
        if start:
            m["day"]["$gte"] = datetime(start.year, start.month, start.day, tzinfo=UTC)
        if end:
            m["day"]["$lt"] = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
    rows = db[coll].aggregate([{"$match": m}, {"$group": {"_id": {"t": "$day", "k": f"${field}"}, "n": {"$sum": "$posts"}}},
                               {"$sort": {"_id.t": 1}}])
    points: dict = {}
    for r in rows:
        points.setdefault(r["_id"]["t"], {"t": r["_id"]["t"]})[r["_id"]["k"]] = r["n"]
    return {"kind": kind, "keys": keys, "series": list(points.values())}


def top_hashtags(db: Database, f: Filters, limit: int = 30) -> dict:
    """All-time (or date-filtered) most used hashtags. Uses hashtag_daily unless other filters need posts."""
    t0 = time.perf_counter()
    if f.needs_live or f.language or f.country or f.sentiment or f.topic or f.mode == "live":
        rows = _agg(db, POSTS, [{"$match": {**POSTS.match(f), "hashtags.0": {"$exists": True}}},
                                {"$unwind": "$hashtags"},
                                {"$group": {"_id": "$hashtags", "posts": {"$sum": 1}, "reach": sum_("$reach")}},
                                {"$sort": {"posts": -1}}, {"$limit": limit}])
        src = "posts"
    else:
        s, e = f.date_range()
        m = {"day": {k: v for k, v in (("$gte", s), ("$lt", e)) if v}} if (s or e) else {}
        rows = list(db[mongo.HASHTAG_DAILY].aggregate([{"$match": m}, {"$group": {"_id": "$hashtag", "posts": {"$sum": "$posts"},
                                                                                  "reach": {"$sum": "$reach"}}},
                                                       {"$sort": {"posts": -1}}, {"$limit": limit}], allowDiskUse=True))
        src = mongo.HASHTAG_DAILY
    return {"items": [{"hashtag": r["_id"], "posts": r["posts"], "reach": r["reach"]} for r in rows],
            "meta": {"source": src, "query_ms": round((time.perf_counter() - t0) * 1000, 1)}}


# --------------------------------------------------------------------------- engagement

def engagement(db: Database, f: Filters, granularity: str = "week", top: int = 10) -> dict:
    t0 = time.perf_counter()
    src = choose_source(f, granularity)
    labels = topic_labels(db)
    match = src.match(f)
    grp = {"posts": sum_(src.count), "engagement": sum_(src.engagement), "likes": sum_(src.likes),
           "comments": sum_(src.comments), "shares": sum_(src.shares), "reach": sum_(src.reach)}
    res = _agg(db, src, [{"$match": match}, {"$facet": {
        "totals": [{"$group": {"_id": None, **grp}}],
        "over_time": [{"$group": {"_id": bucket(src, granularity), **grp}}, {"$sort": {"_id": 1}}],
        "by_sentiment": [{"$group": {"_id": src.sentiment, **grp}}],
        "by_topic": [{"$group": {"_id": src.topic, **grp}}, {"$sort": {"engagement": -1}}, {"$limit": 25}],
    }}])[0]

    def shape(r, key="key"):
        p = r["posts"] or 1
        return {key: r["_id"], "posts": r["posts"], "engagement": r["engagement"], "likes": r["likes"],
                "comments": r["comments"], "shares": r["shares"], "avg_engagement": round(r["engagement"] / p, 2),
                # engagement rate = interactions per 1,000 followers reached
                "engagement_per_1k_reach": round(1000 * r["engagement"] / r["reach"], 3) if r["reach"] else None}

    tot = res["totals"][0] if res["totals"] else {"_id": None, "posts": 0, "engagement": 0, "likes": 0,
                                                    "comments": 0, "shares": 0, "reach": 0}
    by_topic = [shape(r) | {"label": labels.get(r["_id"], {}).get("label", r["_id"])} for r in res["by_topic"]]

    # Top posts: live query that walks the engagement_total index (no in-memory sort).
    pf = POSTS.match(f)
    top_posts = list(db[mongo.POSTS].find({**pf, "engagement.total": {"$gte": f.min_engagement or 0}},
                                          POST_PROJECTION, sort=[("engagement.total", -1)], limit=top))
    return {"totals": shape(tot), "over_time": [shape(r, "t") for r in res["over_time"]],
            "by_sentiment": [shape(r) for r in res["by_sentiment"]], "by_topic": by_topic,
            "top_posts": [serialize_post(p, labels) for p in top_posts],
            "synthetic": engagement_is_synthetic(db), "granularity": granularity,
            "note": "Engagement counts are SYNTHETIC (the source dataset has no likes/replies/retweet counts). "
                    "They depend only on follower count; see scripts/synthesize_engagement.py.",
            "meta": _meta(src, t0)}


# --------------------------------------------------------------------------- geography & language

def geography(db: Database, f: Filters) -> dict:
    t0 = time.perf_counter()
    src = choose_source(f)
    labels = topic_labels(db)
    rows = _agg(db, src, [{"$match": src.match(f)}, {"$facet": {
        "by_country": [{"$group": {"_id": src.country, "posts": sum_(src.count), "reach": sum_(src.reach),
                                   "engagement": sum_(src.engagement),
                                   **{s: sum_({"$cond": [{"$eq": [src.sentiment, s]}, src.count, 0]}) for s in SENTIMENTS}}},
                       {"$sort": {"posts": -1}}],
        "topics": [{"$match": {(src.topic[1:] if isinstance(src.topic, str) else "topic.id"): {"$nin": NON_TOPICS}}},
                   {"$group": {"_id": {"c": src.country, "t": src.topic}, "n": sum_(src.count)}},
                   {"$sort": {"n": -1}},
                   {"$group": {"_id": "$_id.c", "top": {"$push": {"topic": "$_id.t", "posts": "$n"}}}},
                   {"$project": {"top": {"$slice": ["$top", 3]}}}],
    }}])[0]
    top_topics = {r["_id"]: [{**t, "label": labels.get(t["topic"], {}).get("label", t["topic"])} for t in r["top"]]
                  for r in rows["topics"]}
    countries = []
    for r in rows["by_country"]:
        n = r["positive"] + r["neutral"] + r["negative"]
        countries.append({"country": r["_id"], "posts": r["posts"], "reach": r["reach"], "engagement": r["engagement"],
                          "sentiment": {s: r[s] for s in SENTIMENTS},
                          "net_sentiment": round((r["positive"] - r["negative"]) / n, 4) if n else None,
                          "top_topics": top_topics.get(r["_id"], [])})
    known = sum(c["posts"] for c in countries if c["country"] != "Unknown")
    total = sum(c["posts"] for c in countries)
    return {"available": known > 0, "countries": countries, "coverage_pct": _pct(known, total),
            "granularity": "country",
            "note": "Country = the account-level `region` assigned by Salesforce Social Studio in the source data; "
                    "no city-level data exists.", "meta": _meta(src, t0)}


def languages(db: Database, f: Filters) -> dict:
    t0 = time.perf_counter()
    src = choose_source(f)
    labels = topic_labels(db)
    rows = _agg(db, src, [{"$match": src.match(f)}, {"$facet": {
        "by_language": [{"$group": {"_id": src.language, "posts": sum_(src.count), "reach": sum_(src.reach),
                                    **{s: sum_({"$cond": [{"$eq": [src.sentiment, s]}, src.count, 0]}) for s in SENTIMENTS}}},
                        {"$sort": {"posts": -1}}],
        "topics": [{"$match": {(src.topic[1:] if isinstance(src.topic, str) else "topic.id"): {"$nin": NON_TOPICS}}},
                   {"$group": {"_id": {"l": src.language, "t": src.topic}, "n": sum_(src.count)}},
                   {"$sort": {"n": -1}},
                   {"$group": {"_id": "$_id.l", "top": {"$push": {"topic": "$_id.t", "posts": "$n"}}}},
                   {"$project": {"top": {"$slice": ["$top", 5]}}}],
    }}])[0]
    tops = {r["_id"]: [{**t, "label": labels.get(t["topic"], {}).get("label", t["topic"])} for t in r["top"]]
            for r in rows["topics"]}
    total = sum(r["posts"] for r in rows["by_language"]) or 1
    return {"languages": [{"language": r["_id"], "posts": r["posts"], "share_pct": _pct(r["posts"], total),
                           "reach": r["reach"], "sentiment": {s: r[s] for s in SENTIMENTS},
                           "top_topics": tops.get(r["_id"], [])} for r in rows["by_language"]],
            "supported": {"sentiment": ["en"], "topics": ["en", "ru"]},
            "note": "Language comes from the source dataset (Social Studio classification), mapped to ISO 639-1 codes.",
            "meta": _meta(src, t0)}


# --------------------------------------------------------------------------- users

def users(db: Database, limit: int = 20, category: str | None = None) -> dict:
    t0 = time.perf_counter()
    m = {"account_category": category} if category else {}
    top = list(db[mongo.USERS].find(m, sort=[("posts", -1)], limit=limit))
    cats = list(db[mongo.USERS].aggregate([
        {"$group": {"_id": "$account_category", "accounts": {"$sum": 1}, "posts": {"$sum": "$posts"},
                    "avg_retweet_ratio": {"$avg": "$retweet_ratio"},
                    "avg_posts_per_active_day": {"$avg": "$posts_per_active_day"},
                    "positive": {"$sum": "$positive"}, "negative": {"$sum": "$negative"},
                    "neutral": {"$sum": "$neutral"}}},
        {"$sort": {"posts": -1}}]))
    for c in cats:
        n = c["positive"] + c["negative"] + c["neutral"]
        c["net_sentiment"] = round((c["positive"] - c["negative"]) / n, 4) if n else None
        c["avg_retweet_ratio"] = round(c["avg_retweet_ratio"] or 0, 4)
        c["avg_posts_per_active_day"] = round(c["avg_posts_per_active_day"] or 0, 2)
        c["category"] = c.pop("_id")
    for u in top:
        u["username"] = u.pop("_id")
    return {"top_users": top, "categories": cats, "total_users": db[mongo.USERS].estimated_document_count(),
            "meta": {"source": mongo.USERS, "query_ms": round((time.perf_counter() - t0) * 1000, 1)}}


# --------------------------------------------------------------------------- posts

POST_PROJECTION = {"post_id": 1, "text": 1, "created_at": 1, "language": 1, "location": 1, "hashtags": 1,
                   "mentions": 1, "user.username": 1, "user.followers": 1, "user.account_category": 1,
                   "sentiment": 1, "topic": 1, "keywords": 1, "engagement": 1, "is_retweet": 1, "post_type": 1,
                   "quality_flags": 1, "reach": 1}


def serialize_post(p: dict, labels: dict | None = None) -> dict:
    p = dict(p)
    p["id"] = str(p.pop("_id"))
    if p.get("topic") and labels is not None:
        p["topic"]["label"] = labels.get(p["topic"]["id"], {}).get("label", p["topic"].get("label"))
    return p


SORTS = {"newest": [("created_at", -1)], "oldest": [("created_at", 1)], "engagement": [("engagement.total", -1)],
         "relevance": None}


def list_posts(db: Database, f: Filters, page: int = 1, page_size: int = 25, sort: str = "newest",
               with_total: bool = True) -> dict:
    t0 = time.perf_counter()
    match = POSTS.match(f)
    proj = dict(POST_PROJECTION)
    if sort == "relevance" and f.q:
        proj["score"] = {"$meta": "textScore"}
        order = [("score", {"$meta": "textScore"})]
    else:
        order = SORTS.get(sort) or SORTS["newest"]
    cur = db[mongo.POSTS].find(match, proj).sort(order).skip((page - 1) * page_size).limit(page_size)
    items = list(cur)
    total = None
    if with_total:
        # Exact counts on unfiltered queries use collection metadata (O(1)); filtered counts are capped.
        if not match:
            total = db[mongo.POSTS].estimated_document_count()
        else:
            total = db[mongo.POSTS].count_documents(match, limit=100_000)
    labels = topic_labels(db)
    return {"items": [serialize_post(p, labels) for p in items], "page": page, "page_size": page_size,
            "total": total, "total_capped": bool(match) and total == 100_000,
            "meta": {"source": "posts", "query_ms": round((time.perf_counter() - t0) * 1000, 1)}}


def get_post(db: Database, post_id: str) -> dict | None:
    from bson import ObjectId
    from bson.errors import InvalidId

    q: dict = {"post_id": post_id}
    try:
        q = {"$or": [{"_id": ObjectId(post_id)}, {"post_id": post_id}]}
    except (InvalidId, TypeError):
        pass
    doc = db[mongo.POSTS].find_one(q)
    if not doc:
        return None
    # Copy-paste campaign context: how many posts share this exact cleaned text (text_hash index).
    same = db[mongo.POSTS].count_documents({"text_hash": doc.pop("text_hash", None)})
    out = serialize_post(doc, topic_labels(db))
    out["identical_text_posts"] = same
    return out


def filter_options(db: Database) -> dict:
    """Values for dashboard dropdowns, read from the small cube/topics collections."""
    cube = db[mongo.DAILY_CUBE]
    labels = topic_labels(db)
    langs = list(cube.aggregate([{"$group": {"_id": "$language", "n": {"$sum": "$posts"}}}, {"$sort": {"n": -1}}]))
    countries = list(cube.aggregate([{"$group": {"_id": "$country", "n": {"$sum": "$posts"}}}, {"$sort": {"n": -1}}]))
    bounds = dataset_bounds(db)
    return {"languages": [{"value": r["_id"], "posts": r["n"]} for r in langs],
            "countries": [{"value": r["_id"], "posts": r["n"]} for r in countries],
            "topics": [{"value": k, "label": v["label"], "language": v["language"]} for k, v in sorted(labels.items())],
            "sentiments": [*SENTIMENTS, "not_analyzed"], "date_range": bounds}
