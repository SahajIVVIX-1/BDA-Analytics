"""CLI: ingest CSV / JSON / JSONL files into MongoDB.

Examples
  python scripts/ingest.py data/raw/ira538 --profile ira538
  python scripts/ingest.py data/raw/ira538 --limit 100000 --batch-size 5000
  python scripts/ingest.py my_posts.jsonl --profile generic --source my_upload
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database.mongo import get_db  # noqa: E402
from app.database.schema import ensure_posts_collection, init_database  # noqa: E402
from app.ingestion.pipeline import run_ingestion_job  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files or directories")
    ap.add_argument("--profile", default="ira538", choices=["ira538", "generic"])
    ap.add_argument("--source", default=None, help="label stored in each document's `source` field")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None, help="stop after N input records")
    ap.add_argument("--workers", type=int, default=1, help="processes used for cleaning/normalisation")
    ap.add_argument("--drop", action="store_true", help="drop the posts collection first")
    ap.add_argument("--db", default=None, help="database name (default from .env)")
    ap.add_argument("--index-mode", choices=["deferred", "upfront"], default="deferred",
                    help="deferred: load with only the unique post_id index, then build secondary "
                         "indexes (fastest for bulk loads). upfront: create all indexes first.")
    args = ap.parse_args()

    db = get_db(args.db)
    if args.drop:
        db.posts.drop()
        print("dropped posts")
    if args.index_mode == "upfront":
        init_database(db)
    else:
        ensure_posts_collection(db)
        db.posts.create_index("post_id", unique=True, name="uniq_post_id")
    run_ingestion_job(args.paths, profile=args.profile, source=args.source, batch_size=args.batch_size,
                      limit=args.limit, db=db, workers=args.workers, verbose=True)
    if args.index_mode == "deferred":
        t = time.perf_counter()
        init_database(db)
        print(f"Index build: {time.perf_counter() - t:.1f} sec")


if __name__ == "__main__":
    main()
