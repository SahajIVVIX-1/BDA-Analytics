"""Anomaly detection over the daily activity series.

1. Rolling z-score (inside MongoDB): `$setWindowFields` computes, for each day, the
   mean and standard deviation of the previous 28 days (the current day excluded),
   then z = (x - mean) / std. |z| >= threshold marks a spike or drop. Done for
   daily volume and for the daily share of negative posts (sentiment shift).
2. IQR rule on daily volume (global): outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR].
3. Isolation Forest (scikit-learn) on a per-day feature vector
   [log posts, negative share, retweet share, log mean reach]. The daily series is
   small (one row per day), so pulling it into Python is cheap.
"""

from __future__ import annotations

import math
import time

import numpy as np
from pymongo.database import Database

from app.analytics.source import Filters
from app.database import mongo


def daily_features(db: Database, f: Filters) -> list[dict]:
    from app.analytics.source import CUBE

    match = CUBE.match(f)
    return list(db[mongo.DAILY_CUBE].aggregate([
        {"$match": match},
        {"$group": {"_id": "$day", "posts": {"$sum": "$posts"}, "retweets": {"$sum": "$retweets"},
                    "reach": {"$sum": "$reach"},
                    "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, "$posts", 0]}},
                    "analysed": {"$sum": {"$cond": [{"$in": ["$sentiment", ["positive", "neutral", "negative"]]},
                                                    "$posts", 0]}}}},
        {"$set": {"day": "$_id",
                  "neg_share": {"$cond": [{"$gt": ["$analysed", 0]}, {"$divide": ["$negative", "$analysed"]}, None]}}},
        {"$setWindowFields": {
            "sortBy": {"day": 1},
            "output": {
                "vol_mean": {"$avg": "$posts", "window": {"documents": [-28, -1]}},
                "vol_std": {"$stdDevPop": "$posts", "window": {"documents": [-28, -1]}},
                "neg_mean": {"$avg": "$neg_share", "window": {"documents": [-28, -1]}},
                "neg_std": {"$stdDevPop": "$neg_share", "window": {"documents": [-28, -1]}},
                "history": {"$count": {}, "window": {"documents": [-28, -1]}},
            },
        }},
        {"$set": {
            "vol_z": {"$cond": [{"$and": [{"$gte": ["$history", 14]}, {"$gt": ["$vol_std", 0]}]},
                                {"$divide": [{"$subtract": ["$posts", "$vol_mean"]}, "$vol_std"]}, None]},
            "neg_z": {"$cond": [{"$and": [{"$gte": ["$history", 14]}, {"$gt": ["$neg_std", 0]},
                                          {"$gte": ["$analysed", 50]}, {"$ne": ["$neg_share", None]}]},
                                {"$divide": [{"$subtract": ["$neg_share", "$neg_mean"]}, "$neg_std"]}, None]},
        }},
        {"$project": {"_id": 0}},
        {"$sort": {"day": 1}},
    ], allowDiskUse=True))


def detect(db: Database, f: Filters, z_threshold: float = 3.0, contamination: float = 0.02, limit: int = 50,
           min_volume: int = 100) -> dict:
    """min_volume: z-score rules only fire on days where posts or expected posts reach this level,
    so that 2 -> 12 posts in the sparse early years is not reported as a spike."""
    t0 = time.perf_counter()
    days = daily_features(db, f)
    if not days:
        return {"series": [], "anomalies": [], "methods": {}}

    vols = np.array([d["posts"] for d in days], dtype=float)
    q1, q3 = np.percentile(vols, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    iso_flags = np.zeros(len(days), dtype=bool)
    iso_scores = np.zeros(len(days))
    if len(days) >= 30:
        from sklearn.ensemble import IsolationForest

        X = np.array([[math.log1p(d["posts"]), d["neg_share"] if d["neg_share"] is not None else 0.0,
                       d["retweets"] / d["posts"] if d["posts"] else 0.0,
                       math.log1p(d["reach"] / d["posts"]) if d["posts"] else 0.0] for d in days])
        model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42).fit(X)
        iso_flags = model.predict(X) == -1
        iso_scores = -model.score_samples(X)

    series, anomalies = [], []
    for i, d in enumerate(days):
        reasons = []
        big_enough = max(d["posts"], d["vol_mean"] or 0) >= min_volume
        if big_enough and d["vol_z"] is not None and abs(d["vol_z"]) >= z_threshold:
            reasons.append("volume_spike" if d["vol_z"] > 0 else "volume_drop")
        if big_enough and d["neg_z"] is not None and abs(d["neg_z"]) >= z_threshold:
            reasons.append("negativity_surge" if d["neg_z"] > 0 else "negativity_drop")
        if d["posts"] > hi or d["posts"] < lo:
            reasons.append("iqr_outlier")
        if iso_flags[i]:
            reasons.append("isolation_forest")
        row = {"day": d["day"], "posts": d["posts"], "neg_share": round(d["neg_share"], 4) if d["neg_share"] is not None else None,
               "vol_z": round(d["vol_z"], 2) if d["vol_z"] is not None else None,
               "neg_z": round(d["neg_z"], 2) if d["neg_z"] is not None else None,
               "expected": round(d["vol_mean"], 1) if d["vol_mean"] is not None else None,
               "iso_score": round(float(iso_scores[i]), 4), "reasons": reasons}
        series.append(row)
        if reasons:
            anomalies.append(row)
    anomalies.sort(key=lambda r: (-len(r["reasons"]), -abs(r["vol_z"] or 0)))
    return {
        "series": series,
        "anomalies": anomalies[:limit],
        "counts": {"days": len(days), "anomalous_days": len(anomalies),
                   "volume_z": sum(1 for a in anomalies if any(r.startswith("volume") for r in a["reasons"])),
                   "negativity_z": sum(1 for a in anomalies if any(r.startswith("negativity") for r in a["reasons"])),
                   "iqr": sum(1 for a in anomalies if "iqr_outlier" in a["reasons"]),
                   "isolation_forest": int(iso_flags.sum())},
        "methods": {"z_score": f"rolling 28-day window (previous days only), |z| >= {z_threshold}, needs >= 14 days history "
                               f"and >= {min_volume} posts (actual or expected) that day",
                    "iqr": {"q1": q1, "q3": q3, "low": lo, "high": hi},
                    "isolation_forest": f"200 trees, contamination={contamination}, features: log posts, negative share, "
                                        "retweet share, log mean reach"},
        "meta": {"source": mongo.DAILY_CUBE, "query_ms": round((time.perf_counter() - t0) * 1000, 1)},
    }
