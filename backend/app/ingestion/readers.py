"""Streaming readers for CSV / JSONL / JSON files (optionally gzip-compressed).

Readers are generators: they yield one record (dict) at a time so the ingestion
pipeline never holds the whole file in memory. Plain JSON arrays are the one
exception (the format itself needs a full parse); JSONL is recommended for
large files.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path

# Tweets can contain very long fields (quoted threads); lift the default 128 KB limit.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

SUPPORTED_SUFFIXES = {".csv", ".jsonl", ".ndjson", ".json"}


class UnsupportedFormatError(ValueError):
    pass


def detect_format(path: Path) -> str:
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes and suffixes[-1] == ".gz":
        suffixes = suffixes[:-1]
    if not suffixes or suffixes[-1] not in SUPPORTED_SUFFIXES:
        raise UnsupportedFormatError(f"Unsupported file type: {path.name} (use .csv, .jsonl or .json)")
    ext = suffixes[-1]
    return "jsonl" if ext in (".jsonl", ".ndjson") else ext.lstrip(".")


def _open_text(path: Path) -> io.TextIOBase:
    if path.suffix.lower() == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace", newline="")
    return open(path, encoding="utf-8", errors="replace", newline="")


def read_csv(path: Path) -> Iterator[dict]:
    with _open_text(path) as fh:
        yield from csv.DictReader(fh)


def read_jsonl(path: Path) -> Iterator[dict]:
    with _open_text(path) as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # Surface malformed lines to the pipeline as invalid records.
                yield {"__parse_error__": f"line {line_no}: invalid JSON"}
                continue
            yield obj if isinstance(obj, dict) else {"__parse_error__": f"line {line_no}: not an object"}


def read_json(path: Path) -> Iterator[dict]:
    with _open_text(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        # Accept {"posts": [...]} / {"data": [...]} wrappers.
        for key in ("posts", "data", "records", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    for obj in data:
        yield obj if isinstance(obj, dict) else {"__parse_error__": "array item is not an object"}


def iter_records(path: str | Path) -> Iterator[dict]:
    path = Path(path)
    fmt = detect_format(path)
    if fmt == "csv":
        return read_csv(path)
    if fmt == "jsonl":
        return read_jsonl(path)
    return read_json(path)


def expand_paths(paths: list[str | Path]) -> list[Path]:
    """Expand directories into their supported files (sorted naturally by trailing number)."""
    import re

    def natural(p: Path):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]

    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files = [f for f in p.iterdir() if f.is_file() and _supported(f)]
            out.extend(sorted(files, key=natural))
        else:
            out.append(p)
    return out


def _supported(p: Path) -> bool:
    try:
        detect_format(p)
        return True
    except UnsupportedFormatError:
        return False
