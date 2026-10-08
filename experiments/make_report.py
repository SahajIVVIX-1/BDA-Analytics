"""Render docs/performance.md from the measured JSON files in experiments/results/.

Every number in the generated document is read from those files; nothing is typed in by hand.
Experiments that have not been run are listed as "not measured".

    python experiments/make_report.py                 # writes docs/performance.md
    python experiments/make_report.py --out other.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "experiments" / "results"


def load(name: str) -> dict | None:
    p = RESULTS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.0f}" if v.is_integer() and abs(v) >= 1000 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def to_md(df: pd.DataFrame) -> str:
    """DataFrame -> GitHub markdown table (no extra dependency such as tabulate)."""
    num = [pd.api.types.is_numeric_dtype(df[c]) for c in df.columns]
    lines = ["| " + " | ".join(map(str, df.columns)) + " |",
             "| " + " | ".join("---:" if n else "---" for n in num) + " |"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(_cell(v.item() if hasattr(v, "item") else v) for v in row) + " |")
    return "\n".join(lines)


def table(rows: list[dict], columns: dict[str, str]) -> str:
    """Markdown table of the selected columns, renamed for readers."""
    return to_md(pd.DataFrame(rows)[list(columns)].rename(columns=columns))


def hardware_line(d: dict) -> str:
    h = d["hardware"]
    return (f"Measured on **{h.get('label') or 'unlabelled machine'}**: {h.get('processor') or h.get('machine')}, "
            f"{h.get('cpu_count')} logical CPUs, {h.get('ram_gb')} GB RAM, {h.get('os')}, Python {h.get('python')}, "
            f"MongoDB {h.get('mongodb')} (WiredTiger cache {h.get('wiredtiger_cache_gb')} GB). "
            f"Run at {d['run_at'][:19].replace('T', ' ')} UTC, took {d['duration_sec']:,.0f} s.")


def not_measured(cmd: str) -> str:
    return f"_Not measured yet._ Run `python experiments/run_experiments.py {cmd}`.\n"


def section_ingestion() -> str:
    out = ["## 1. Ingestion scaling\n\n",
           "CSV files are streamed, cleaned and normalised in a process pool, and bulk-inserted with "
           "`insert_many(ordered=False)` into a fresh database. Secondary indexes are built after the load "
           "(see experiment 4 for why).\n\n"]
    d = load("ingestion_scaling")
    if not d:
        return "".join(out) + not_measured("ingestion")
    out += [hardware_line(d), "\n\n", f"Parameters: `{json.dumps(d['params'])}`\n\n"]
    out.append(table(d["results"], {
        "total_read": "Records read", "inserted": "Inserted", "duplicates": "Duplicates", "invalid": "Invalid",
        "elapsed_sec": "Load time (s)", "records_per_sec": "Records/s", "index_build_sec": "Index build (s)",
        "total_sec_including_indexes": "Total (s)", "data_mb": "Data (MB)", "storage_mb": "On disk (MB)",
        "index_mb": "Indexes (MB)"}))
    rps = [r["records_per_sec"] for r in d["results"]]
    if len(rps) > 1:
        out.append(f"\n\nAcross these sizes throughput ranged from {min(rps):,.0f} to {max(rps):,.0f} records/s "
                   f"(largest / smallest = {max(rps) / min(rps):.2f}).\n")
    else:
        out.append("\n")
    return "".join(out)


def section_simple(name: str, title: str, cmd: str, intro: str, cols: dict[str, str]) -> str:
    out = [f"## {title}\n\n", intro, "\n\n"]
    d = load(name)
    if not d:
        return "".join(out) + not_measured(cmd)
    out += [hardware_line(d), "\n\n", f"Parameters: `{json.dumps(d['params'])}`\n\n", table(d["results"], cols), "\n"]
    return "".join(out)


def section_indexes() -> str:
    out = ["## 5. Indexed query vs collection scan\n\n",
           "Each query runs with `explain('executionStats')` twice: once forced to a collection scan with "
           "`hint({$natural: 1})`, once with the named index. Times are MongoDB's own `executionTimeMillis` "
           "(median of the runs), so they exclude network and Python overhead.\n\n"]
    d = load("index_vs_collscan")
    if not d:
        return "".join(out) + not_measured("queries")
    out += [hardware_line(d), "\n\n", f"Parameters: `{json.dumps(d['params'])}`\n\n"]
    rows = [{**r, "speedup": r["speedup"] if r["indexed_ms"] >= 1 else None} for r in d["results"]]
    out.append(table(rows, {
        "size": "Size", "query": "Query", "index": "Index", "collscan_ms": "Scan (ms)",
        "collscan_docs_examined": "Scan docs examined", "indexed_ms": "Index (ms)",
        "indexed_keys_examined": "Index keys examined", "indexed_docs_examined": "Index docs examined",
        "indexed_n_returned": "Returned", "speedup": "Speed-up (x)"}))
    out.append("\n\nA collection scan always examines every document, so its cost grows with the collection. "
               "An index examines only the keys it needs, so its cost follows the size of the answer instead. "
               "An index time of 0 ms means below MongoDB's 1 ms timer resolution; no speed-up is computed for those rows. "
               "The `user_timeline_top50` account does not occur in the smaller subsets, so it returns 0 rows there.\n")
    return "".join(out)


def section_aggregations() -> str:
    out = ["## 6. Aggregation pipelines\n\n",
           "Median wall-clock time of the complete `aggregate()` call from Python, on copies of the first N posts "
           "(in ingestion order, i.e. source-file order, not a random sample).\n\n"]
    d = load("aggregation_scaling")
    if not d:
        return "".join(out) + not_measured("aggregations")
    r = d["results"]
    out += [hardware_line(d), "\n\n"]
    df = pd.DataFrame(r["pipelines"]).pivot_table(index="pipeline", columns="documents", values="ms", sort=False)
    df.columns = [f"{c:,} docs (ms)" for c in df.columns]
    out += [to_md(df.reset_index().rename(columns={"pipeline": "Pipeline"})), "\n\n"]
    out.append("### 6b. Pre-aggregated rollups vs live aggregation (full collection)\n\n"
               "The same dashboard query answered from the `posts` collection (`mode=live`) and from the "
               "`daily_cube` rollup (`mode=cube`). The two modes return the same counts (checked on test data by "
               "`backend/tests/test_api.py::test_cube_and_live_agree`); the cube simply has far fewer documents to read.\n\n")
    out += [table(r["cube_vs_live"], {"query": "Query", "live_ms": "Live on posts (ms)", "cube_ms": "Rollup (ms)",
                                       "speedup": "Speed-up (x)"}), "\n\n"]
    rb = r["rollup_build"]
    rows = [{"collection": k, "seconds": v["seconds"], "documents": v["documents"]} for k, v in rb.items() if isinstance(v, dict)]
    out.append(f"### 6c. Full rollup rebuild ({rb['total_sec']:,.1f} s in total)\n\n")
    out += [table(rows, {"collection": "Rollup collection", "seconds": "Build time (s)", "documents": "Documents"}), "\n\n"]
    sizes = [{"collection": k, "documents": v} for k, v in r["collection_sizes"].items()]
    out += ["Collection sizes at the time of the run:\n\n", table(sizes, {"collection": "Collection", "documents": "Documents"}), "\n"]
    return "".join(out)


def section_nlp() -> str:
    out = ["## 7. NLP throughput\n\n",
           "Model-only throughput on a random sample of English posts, then the end-to-end enrichment job "
           "(read from MongoDB, sentiment + topics + keywords, bulk `UpdateOne` writes) on a copy of the data.\n\n"]
    d = load("nlp_throughput")
    if not d:
        return "".join(out) + not_measured("nlp")
    r = d["results"]
    out += [hardware_line(d), "\n\n", f"Parameters: `{json.dumps(d['params'])}`\n\n"]
    out += [table(r["models"], {"task": "Task", "texts": "Texts", "ms": "Time (ms)", "texts_per_sec": "Texts/s"}), "\n\n"]
    out += [table(r["end_to_end"], {"workers": "Worker processes", "posts": "Posts", "elapsed_sec": "Time (s)",
                                    "db_write_sec": "of which DB writes (s)", "posts_per_sec": "Posts/s"}), "\n"]
    return "".join(out)


def section_models() -> str:
    out = ["## 8. Sentiment model evaluation\n\n"]
    d = load("sentiment_evaluation")
    if not d:
        return "".join(out) + "_Not measured yet._ Run `python scripts/train_sentiment.py`.\n"
    rows = [{"model": k, **{m: v.get(m) for m in ("validation_macro_f1", "macro_f1", "accuracy", "macro_recall", "texts_per_second")}}
            for k, v in d["results"].items()]
    out += [f"Dataset: {d['dataset']}; sizes {d['sizes']}. Selection: {d['selection_metric']}. "
            f"Chosen model: **{d['best_model']}**.\n\n",
            table(rows, {"model": "Model", "validation_macro_f1": "Validation macro-F1", "macro_f1": "Test macro-F1",
                         "accuracy": "Test accuracy", "macro_recall": "Test macro recall", "texts_per_second": "Texts/s"}),
            "\n\nThese scores are on TweetEval (general tweets), not on the IRA tweets, which have no sentiment labels. "
            "How well the model transfers to the IRA data has not been measured.\n"]
    return "".join(out)


def total_runtime() -> str:
    names = ["ingestion_scaling", "ingestion_batch_size", "ingestion_workers", "ingestion_index_mode",
             "index_vs_collscan", "aggregation_scaling", "nlp_throughput"]
    found = [d for d in map(load, names) if d]
    if not found:
        return ""
    return (f"The run recorded above took {sum(d['duration_sec'] for d in found) / 60:,.0f} minutes in total "
            f"on {found[0]['hardware'].get('label') or 'that machine'}. ")


def build() -> str:
    parts = [
        "# Performance experiments\n\n",
        "_Generated by `experiments/make_report.py` from `experiments/results/*.json`. Do not edit by hand; "
        "re-run the experiments and regenerate instead._\n\n",
        "All timings are single-machine measurements: one `mongod` process, no sharding, no replication. "
        "The 5M-document size from the brief was **not measured**: the real dataset has 2.95M tweets, and the "
        "project does not pad it with synthetic posts. See *Running on your laptop* at the end.\n\n"
        "Run notes for the results recorded in this repository: the API server was running but idle during the run, "
        "and the backend test suite (a few seconds of load on a separate test database) ran once during the "
        "2.95M ingestion step. The NLP experiment was re-run on its own after a code change broke its 2- and "
        "4-worker steps mid-run; its timestamp therefore differs from the others.\n\n",
        section_ingestion(), "\n",
        section_simple("ingestion_batch_size", "2. Batch size", "batch",
                       "Same input loaded with different `insert_many` batch sizes.",
                       {"batch_size": "Batch size", "inserted": "Inserted", "elapsed_sec": "Time (s)",
                        "records_per_sec": "Records/s"}), "\n",
        section_simple("ingestion_workers", "3. Parallel cleaning", "workers",
                       "Number of processes that clean and normalise records while the parent process inserts.",
                       {"workers": "Worker processes", "inserted": "Inserted", "elapsed_sec": "Time (s)",
                        "records_per_sec": "Records/s"}), "\n",
        section_simple("ingestion_index_mode", "4. When to build indexes", "indexmode",
                       "`upfront`: all 12 secondary indexes exist during the load. `deferred`: only the unique "
                       "`post_id` index during the load, the rest built afterwards.",
                       {"index_mode": "Mode", "inserted": "Inserted", "elapsed_sec": "Load (s)",
                        "index_build_sec": "Index build (s)", "total_sec_including_indexes": "Total (s)",
                        "records_per_sec": "Load records/s"}), "\n",
        section_indexes(), "\n", section_aggregations(), "\n", section_nlp(), "\n", section_models(), "\n",
        "## Running on your laptop\n\n"
        "Numbers depend on the machine, so re-run the experiments on the laptop you will present with and label them:\n\n"
        "```bash\n"
        "cd backend\n"
        "set BENCH_MACHINE_LABEL=My laptop (16 GB)        # PowerShell: $env:BENCH_MACHINE_LABEL=\"My laptop (16 GB)\"\n"
        "python ../experiments/run_experiments.py all\n"
        "python ../experiments/make_report.py\n"
        "```\n\n"
        f"{total_runtime()}Use `--sizes 100000 500000` and `--runs 1` for a shorter run. The experiments create and drop their own "
        "`bench_*` databases; the main `social_analytics` database is only read, except that the aggregation "
        "experiment rebuilds the rollup collections (same contents).\n",
    ]
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "performance.md")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
