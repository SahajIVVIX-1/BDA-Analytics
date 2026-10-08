"""Download the two public datasets the project uses into data/raw/.

  data/raw/ira538/     FiveThirtyEight "russian-troll-tweets": 13 CSV files, about 1 GB, ~2.95M tweets
  data/raw/tweeteval/  TweetEval sentiment split (train / val / test), used only to train and evaluate
                       the sentiment model

    python scripts/download_data.py              # both
    python scripts/download_data.py --only ira538
    python scripts/download_data.py --only tweeteval

Files that already exist with a non-zero size are skipped, so the script can be re-run after an interruption.
Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IRA_BASE = "https://raw.githubusercontent.com/fivethirtyeight/russian-troll-tweets/master/"
IRA_FILES = [f"IRAhandle_tweets_{i}.csv" for i in range(1, 14)]
TWEETEVAL_BASE = "https://raw.githubusercontent.com/cardiffnlp/tweeteval/main/datasets/sentiment/"
TWEETEVAL_FILES = ["mapping.txt"] + [f"{split}_{kind}.txt" for split in ("train", "val", "test")
                                     for kind in ("text", "labels")]


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip {dest.name} (exists)")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  get  {url}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    tmp.replace(dest)
    print(f"       {dest.stat().st_size / 1e6:,.1f} MB")


def download(base: str, files: list[str], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in files:
        fetch(base + name, folder / name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=["ira538", "tweeteval"])
    args = ap.parse_args()
    try:
        if args.only in (None, "ira538"):
            print("FiveThirtyEight russian-troll-tweets -> data/raw/ira538")
            download(IRA_BASE, IRA_FILES, ROOT / "data" / "raw" / "ira538")
        if args.only in (None, "tweeteval"):
            print("TweetEval sentiment -> data/raw/tweeteval")
            download(TWEETEVAL_BASE, TWEETEVAL_FILES, ROOT / "data" / "raw" / "tweeteval")
    except OSError as e:
        sys.exit(f"download failed: {e}")
    print("done")


if __name__ == "__main__":
    main()
