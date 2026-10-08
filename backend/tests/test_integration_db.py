"""Ingestion, schema, indexes and rollups against a real (throwaway) MongoDB database."""

import pytest
from pymongo.errors import WriteError

from app.ingestion.pipeline import ingest_records
from tests.conftest import make_records

pytestmark = pytest.mark.integration


def test_ingestion_counts(loaded_db):
    db, stats = loaded_db
    expected = len(make_records())
    assert stats.inserted == expected
    assert db.posts.count_documents({}) == expected


def test_reingest_is_deduplicated(loaded_db):
    db, _ = loaded_db
    before = db.posts.count_documents({})
    again = ingest_records(make_records()[:50], db=db, profile="generic", source="test", batch_size=20)
    assert again.inserted == 0 and again.duplicates == 50
    assert db.posts.count_documents({}) == before


def test_invalid_records_are_counted_not_inserted(loaded_db):
    db, _ = loaded_db
    stats = ingest_records([{"id": "bad1", "text": "", "created_at": "2016-01-01"},
                            {"id": "bad2", "text": "fine", "created_at": "nope"}],
                           db=db, profile="generic", source="test")
    assert stats.inserted == 0
    assert db.posts.count_documents({"post_id": {"$in": ["bad1", "bad2"]}}) == 0


def test_schema_validator_rejects_bad_document(loaded_db):
    db, _ = loaded_db
    with pytest.raises(WriteError):
        db.posts.insert_one({"post_id": "x", "text": "missing required fields"})


def test_indexed_query_uses_index(loaded_db):
    db, _ = loaded_db
    plan = db.posts.find({"hashtags": "election"}).explain()
    winning = str(plan["queryPlanner"]["winningPlan"])
    assert "IXSCAN" in winning and "hashtags" in winning


def test_daily_cube_matches_posts(loaded_db):
    db, _ = loaded_db
    cube_total = next(db.daily_cube.aggregate([{"$group": {"_id": None, "n": {"$sum": "$posts"}}}]))["n"]
    assert cube_total == db.posts.count_documents({"processed": True})
    tag_total = next(db.hashtag_daily.aggregate([{"$match": {"hashtag": "news"}},
                                                 {"$group": {"_id": None, "n": {"$sum": "$posts"}}}]))["n"]
    assert tag_total == db.posts.count_documents({"hashtags": "news"})


@pytest.mark.parametrize("method", ["fork", "spawn"])
def test_parallel_ingestion_with_each_start_method(loaded_db, monkeypatch, method):
    """Workers > 1 must work with fork (Linux/macOS) and spawn (the only option on Windows)."""
    import multiprocessing as mp

    from app.ingestion import pipeline

    if method not in mp.get_all_start_methods():
        pytest.skip(f"{method} not available on this OS")
    db, _ = loaded_db
    monkeypatch.setattr(pipeline, "mp_context", lambda: mp.get_context(method))
    recs = [{**r, "id": f"{method}-{r['id']}"} for r in make_records(n_days=3, per_day=20)]
    stats = ingest_records(recs, db=db, profile="generic", source="test", batch_size=10, workers=2)
    assert stats.inserted == len(recs)
    db.posts.delete_many({"post_id": {"$regex": f"^{method}-"}})
