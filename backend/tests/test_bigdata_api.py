"""Big Data Lab endpoints: they read result files and the lake folder, so no MongoDB is needed."""

import json

from fastapi.testclient import TestClient

from app.api import bigdata
from app.main import app

client = TestClient(app)


def test_results_reports_missing_experiments(tmp_path, monkeypatch):
    monkeypatch.setattr(bigdata, "RESULTS_DIR", tmp_path)
    (tmp_path / "spark_pipeline.json").write_text(json.dumps({"rows": {"raw": 10}}))
    (tmp_path / "sharding.json").write_text("{not json")  # unreadable files are skipped, not fatal
    body = client.get("/api/bigdata/results").json()
    assert body["results"]["spark_pipeline"]["rows"]["raw"] == 10
    assert "sharding" in body["missing"] and "spark_pipeline" not in body["missing"]


def test_lake_lists_layers_tables_and_partitions(tmp_path, monkeypatch):
    monkeypatch.setattr(bigdata, "LAKE_DIR", tmp_path)
    for year, month in [(2016, m) for m in range(1, 9)]:
        part = tmp_path / "silver" / "posts" / f"year={year}" / f"month={month}"
        part.mkdir(parents=True)
        (part / "part-0.parquet").write_bytes(b"x" * 100)
        (part / "_SUCCESS").write_bytes(b"")  # Spark marker files are not counted
    layers = {x["layer"]: x for x in client.get("/api/bigdata/lake").json()["layers"]}
    assert layers["bronze"]["exists"] is False
    posts = layers["silver"]["tables"][0]
    assert posts["files"] == 8 and posts["bytes"] == 800 and posts["partitions"] == 8
    assert posts["partition_sample"][3] == "…" and len(posts["partition_sample"]) == 7


def test_cluster_offline_is_not_an_error(monkeypatch):
    monkeypatch.setenv("MONGOS_URI", "mongodb://127.0.0.1:1")
    body = client.get("/api/bigdata/cluster").json()
    assert body["online"] is False and "docker-compose.bigdata.yml" in body["hint"]
