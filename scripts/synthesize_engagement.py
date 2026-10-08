"""Add SYNTHETIC engagement counts (likes / comments / shares) to posts that have none.

WHY: the FiveThirtyEight dataset does not include likes, replies or retweet
counts. The engagement module of the platform still needs numbers to be
exercised end to end, so this script generates them.

HONESTY RULES
  * Every generated value is stored with `engagement.synthetic = true`.
  * The API returns `synthetic: true` with every engagement figure and the
    dashboard shows a "Synthetic data" badge on every engagement chart.
  * Generated values depend ONLY on the author's real follower count, whether
    the post is a retweet, and a seed derived from the post id. They do NOT
    depend on sentiment, topic, hashtags or time, so any pattern in
    "engagement by sentiment/topic" reflects only differences in follower
    counts between groups, never a real audience reaction. Do not draw
    conclusions about real engagement from these numbers.
  * Posts that already have engagement (e.g. from an uploaded dataset) are
    never touched.

MODEL (per post, deterministic given post_id)
  rng       = PCG64(seed = blake2b(post_id) XOR global_seed)
  base      = 0.004 * followers ** 0.85            (larger accounts get more interaction)
  likes     = floor(base * LogNormal(0, 1.1))
  shares    = Binomial(likes, Uniform(0.10, 0.35))
  comments  = Binomial(likes, Uniform(0.02, 0.12))
  retweets of other accounts' posts get 10% of the above (credit goes to the original post)
  total     = likes + comments + shares

  python scripts/synthesize_engagement.py            # all posts with engagement == null
  python scripts/synthesize_engagement.py --remove   # delete synthetic engagement again
"""
import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from pymongo import UpdateOne  # noqa: E402

from app.database.mongo import get_db  # noqa: E402

GLOBAL_SEED = 20261008


def engagement_for(post_id: str, followers: int | None, is_retweet: bool) -> dict:
    seed = int.from_bytes(hashlib.blake2b(post_id.encode(), digest_size=8).digest(), "little") ^ GLOBAL_SEED
    rng = np.random.default_rng(seed)
    base = 0.004 * float(followers or 0) ** 0.85
    if is_retweet:
        base *= 0.1
    likes = int(base * rng.lognormal(0.0, 1.1))
    shares = int(rng.binomial(likes, rng.uniform(0.10, 0.35))) if likes else 0
    comments = int(rng.binomial(likes, rng.uniform(0.02, 0.12))) if likes else 0
    return {"likes": likes, "comments": comments, "shares": shares, "total": likes + comments + shares,
            "synthetic": True, "generator": "scripts/synthesize_engagement.py v1"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    posts = get_db(args.db).posts

    if args.remove:
        res = posts.update_many({"engagement.synthetic": True}, {"$set": {"engagement": None}})
        print(f"removed synthetic engagement from {res.modified_count:,} posts")
        return

    t0 = time.perf_counter()
    cursor = posts.find({"engagement": None}, {"post_id": 1, "user.followers": 1, "is_retweet": 1},
                        sort=[("_id", 1)], batch_size=args.batch_size).hint([("_id", 1)])
    ops, n = [], 0
    for d in cursor:
        e = engagement_for(d["post_id"], d.get("user", {}).get("followers"), d.get("is_retweet", False))
        ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"engagement": e}}))
        if len(ops) >= args.batch_size:
            posts.bulk_write(ops, ordered=False)
            n += len(ops)
            ops = []
            if n % 200_000 == 0:
                print(f"  ... {n:,}", flush=True)
    if ops:
        posts.bulk_write(ops, ordered=False)
        n += len(ops)
    print(f"synthetic engagement written to {n:,} posts in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
