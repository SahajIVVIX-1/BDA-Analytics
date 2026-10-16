#!/usr/bin/env bash
# Run the whole Big Data Lab in Docker (macOS / Linux). Same steps as scripts/bigdata.ps1.
#   scripts/bigdata.sh                 # everything
#   SHARD_DOCS=all scripts/bigdata.sh  # load every post into the sharded cluster
set -euo pipefail
cd "$(dirname "$0")/.."
export BENCH_MACHINE_LABEL="${BENCH_MACHINE_LABEL:-Docker on $(hostname)}"
dc() { docker compose -f docker-compose.bigdata.yml "$@"; }

dc build spark
dc run --rm --no-deps spark python scripts/download_data.py --only ira538
dc run --rm --no-deps spark python -m bigdata.spark.pipeline
[[ "${SKIP_BENCHMARKS:-}" == "1" ]] || dc run --rm --no-deps spark python -m bigdata.spark.benchmarks all
dc up -d   # cluster starts after the Spark-only steps so they never compete for memory
dc run --rm spark python -m bigdata.sharding.cluster init
dc run --rm spark python -m bigdata.sharding.experiment --size "${SHARD_DOCS:-500000}"
echo "Done. Open the dashboard's Big Data Lab page to see the results."
