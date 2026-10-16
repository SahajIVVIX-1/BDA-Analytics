"""Zip the data lake for a GitHub release, so the Parquet output does not have to be rebuilt.

    python scripts/package_lake.py              # silver + gold + experiment results
    python scripts/package_lake.py --bronze     # also bronze (about 0.5 GB more)

Writes dist/release/lake-<layer>.zip (Parquet is already compressed, so files are stored, not deflated)
and prints the `gh release create` command. Unzip into the project root to restore data/lake/.
Uses only the standard library.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "release"


def zip_dir(src: Path, dest: Path, method=zipfile.ZIP_STORED) -> None:
    with zipfile.ZipFile(dest, "w", method, allowZip64=True) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".crc"):
                z.write(p, p.relative_to(ROOT).as_posix())
    print(f"  {dest.relative_to(ROOT)}  {dest.stat().st_size / 1e6:,.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bronze", action="store_true", help="include the bronze layer")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    layers = ["silver", "gold"] + (["bronze"] if args.bronze else [])
    for layer in layers:
        src = ROOT / "data" / "lake" / layer
        if not src.exists():
            raise SystemExit(f"{src} does not exist: run python -m bigdata.spark.pipeline first")
        zip_dir(src, OUT / f"lake-{layer}.zip")
    zip_dir(ROOT / "experiments" / "results", OUT / "experiment-results.zip", zipfile.ZIP_DEFLATED)
    files = " ".join(f"dist/release/{p.name}" for p in sorted(OUT.glob("*.zip")))
    print("\nUpload with:\n  gh release create lake-v1 " + files +
          ' --title "Data lake snapshot" --notes-file docs/release-notes.md')


if __name__ == "__main__":
    main()
