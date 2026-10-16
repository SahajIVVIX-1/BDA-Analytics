# Run the whole Big Data Lab in Docker on Windows: Spark lake pipeline, benchmarks, sharded cluster experiment.
# Needs only Docker Desktop (running). From the project root:
#
#   powershell -ExecutionPolicy Bypass -File scripts\bigdata.ps1                 # everything
#   powershell -ExecutionPolicy Bypass -File scripts\bigdata.ps1 -SkipBenchmarks # pipeline + sharding only
#   powershell -ExecutionPolicy Bypass -File scripts\bigdata.ps1 -ShardDocs all  # load all posts (needs > 4 GB for Docker)
#
# Results go to experiments/results/*.json, the lake to data/lake/. Stop the cluster afterwards with
#   docker compose -f docker-compose.bigdata.yml down
param(
    [string]$ShardDocs = "500000",
    [switch]$SkipDownload,
    [switch]$SkipBenchmarks,
    [switch]$SkipSharding,
    [string]$Label = "Docker Desktop on $env:COMPUTERNAME"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:BENCH_MACHINE_LABEL = $Label

function Step($title, [string[]]$cmd) {
    Write-Host "`n== $title" -ForegroundColor Cyan
    & docker compose -f docker-compose.bigdata.yml @cmd
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $title (exit $LASTEXITCODE)" }
}

docker info --format "{{.ServerVersion}}" *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker is not running. Start Docker Desktop and try again." }

Step "Build the Spark image" @("build", "spark")
if (-not $SkipDownload) { Step "Download the dataset (skips files already present)" @("run", "--rm", "--no-deps", "spark", "python", "scripts/download_data.py", "--only", "ira538") }
Step "Spark pipeline: raw CSV -> bronze -> silver -> gold" @("run", "--rm", "--no-deps", "spark", "python", "-m", "bigdata.spark.pipeline")
if (-not $SkipBenchmarks) { Step "Spark and data-lake benchmarks" @("run", "--rm", "--no-deps", "spark", "python", "-m", "bigdata.spark.benchmarks", "all") }
if (-not $SkipSharding) {
    # The cluster starts after the Spark-only steps so Spark and six mongod processes never compete for memory.
    Step "Start the sharded MongoDB cluster" @("up", "-d")
    Step "Initialise the cluster (replica sets + addShard)" @("run", "--rm", "spark", "python", "-m", "bigdata.sharding.cluster", "init")
    Step "Sharding experiment ($ShardDocs posts)" @("run", "--rm", "spark", "python", "-m", "bigdata.sharding.experiment", "--size", $ShardDocs)
}
Write-Host "`nDone. Open the dashboard's Big Data Lab page to see the results." -ForegroundColor Green
