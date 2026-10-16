"""Shared helpers for the Spark jobs and Big Data experiments.

Paths, the Spark session factory, hardware info and result writing live here so every
job and benchmark records results in the same shape as experiments/run_experiments.py.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "ira538"
LAKE_DIR = Path(os.environ.get("LAKE_DIR", ROOT / "data" / "lake"))
BRONZE = LAKE_DIR / "bronze" / "posts"
SILVER = LAKE_DIR / "silver" / "posts"
GOLD = LAKE_DIR / "gold"
RESULTS = ROOT / "experiments" / "results"

# The backend's language table is reused so Spark and the Python pipeline agree on codes.
sys.path.insert(0, str(ROOT / "backend"))


def spark_session(app: str, cores: int | str = "*", memory: str | None = None,
                  shuffle_partitions: int | None = None):
    """Local Spark session. `cores` maps to master local[N]: one executor thread per core."""
    from pyspark.sql import SparkSession

    # Python workers must use this interpreter (with pymongo installed), not whatever "python3" is on PATH.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    memory = memory or os.environ.get("SPARK_DRIVER_MEMORY", "6g")
    n = os.cpu_count() if cores == "*" else int(cores)
    builder = (SparkSession.builder.appName(app)
               .master(f"local[{cores}]")
               .config("spark.driver.memory", memory)
               # Small shuffles on one machine: 4 partitions per core instead of the default 200.
               .config("spark.sql.shuffle.partitions", str(shuffle_partitions or max(4, n * 4)))
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.sql.parquet.compression.codec", "snappy")
               .config("spark.sql.adaptive.enabled", "true")
               .config("spark.ui.showConsoleProgress", "false"))
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def hardware(spark=None) -> dict:
    info = {"os": platform.platform(), "python": platform.python_version(), "cpu_count": os.cpu_count(),
            "machine": platform.machine(), "processor": platform.processor() or None}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["processor"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        info["ram_gb"] = round(pages / 1024 ** 3, 1)
    except (ValueError, OSError, AttributeError):
        pass
    if spark is not None:
        info["spark"] = spark.version
        info["java"] = spark.sparkContext._jvm.System.getProperty("java.version")
    info["label"] = os.environ.get("BENCH_MACHINE_LABEL") or platform.node()
    return info


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.name.startswith((".", "_")))


def file_count(path: Path, suffix: str = ".parquet") -> int:
    return sum(1 for _ in path.rglob(f"*{suffix}")) if path.exists() else 0


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


@contextmanager
def timer(store: dict, key: str):
    t = time.perf_counter()
    yield
    store[key] = round(time.perf_counter() - t, 3)


def write_result(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"experiment": name, "run_at": datetime.now(UTC).isoformat(), **payload}
    out = RESULTS / f"{name}.json"
    out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {out.relative_to(ROOT)}")
    return out
