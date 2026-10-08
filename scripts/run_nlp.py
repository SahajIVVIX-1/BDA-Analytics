"""CLI: run sentiment + topic enrichment over unprocessed posts.

  python scripts/run_nlp.py --workers 4
  python scripts/run_nlp.py --reprocess --sentiment vader   # recompute everything with VADER
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database.mongo import get_db  # noqa: E402
from app.nlp.enrich import run_enrichment  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sentiment", default="tfidf_logreg", choices=["tfidf_logreg", "vader"])
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reprocess", action="store_true", help="also re-run already processed posts")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    res = run_enrichment(get_db(args.db), sentiment_method=args.sentiment, batch_size=args.batch_size,
                         workers=args.workers, limit=args.limit, reprocess=args.reprocess, verbose=True)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
