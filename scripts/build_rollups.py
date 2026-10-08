"""CLI: (re)build the pre-aggregated analytics collections with MongoDB $merge pipelines.

  python scripts/build_rollups.py                          # full rebuild
  python scripts/build_rollups.py --start 2017-01-01 --end 2017-02-01   # incremental (only those days)
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.analytics.rollups import build_all  # noqa: E402
from app.database.mongo import get_db  # noqa: E402


def day(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=day)
    ap.add_argument("--end", type=day, help="exclusive")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    print(json.dumps(build_all(get_db(args.db), args.start, args.end, verbose=True), indent=2))


if __name__ == "__main__":
    main()
