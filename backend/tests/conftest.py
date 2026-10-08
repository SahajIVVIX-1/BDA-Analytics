"""Shared fixtures.

Unit tests need nothing. Integration tests (marked `integration`) need a running MongoDB
at MONGO_URI; they use a throwaway database `social_analytics_test` that is dropped
before and after the session, so the real data is never touched.
"""

import os
import random
from datetime import UTC, datetime, timedelta

import pytest

os.environ["MONGO_DB"] = "social_analytics_test"  # must be set before app.config is imported

TEST_DB = "social_analytics_test"


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs a running MongoDB (skipped if none)")


def make_records(n_days: int = 60, per_day: int = 8, seed: int = 7) -> list[dict]:
    """Small synthetic records in the generic upload format (used only by the tests)."""
    rng = random.Random(seed)
    start = datetime(2016, 1, 1, tzinfo=UTC)
    tags = ["election", "news", "sports", "music"]
    words = {"en": ["great day for the team", "terrible news about the election", "watching the game tonight",
                    "breaking news from the city"],
             "ru": ["новости дня", "отличная погода сегодня"]}
    recs, i = [], 0
    for d in range(n_days):
        # day 45 is a deliberate volume spike for the anomaly test
        count = per_day * 10 if d == 45 else per_day + rng.randint(-3, 3)
        for _ in range(count):
            lang = "en" if rng.random() < 0.8 else "ru"
            tag = rng.choice(tags)
            text = f"{rng.choice(words[lang])} #{tag} @user{rng.randint(1, 5)} https://t.co/x{i}"
            ts = start + timedelta(days=d, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            recs.append({"id": f"t{i}", "text": text, "created_at": ts.isoformat(), "lang": lang,
                         "country": rng.choice(["United States", "Germany", ""]),
                         "username": f"acct{rng.randint(1, 12)}", "followers": rng.randint(10, 5000),
                         "likes": rng.randint(0, 50), "replies": rng.randint(0, 5), "retweets": rng.randint(0, 20)})
            i += 1
    return recs


@pytest.fixture(scope="session")
def mongo_db():
    from app.database import mongo

    if not mongo.ping():
        pytest.skip("MongoDB is not reachable")
    client = mongo.get_client()
    client.drop_database(TEST_DB)
    yield client[TEST_DB]
    mongo.get_client().drop_database(TEST_DB)  # the app's shutdown may have closed the first client


@pytest.fixture(scope="session")
def loaded_db(mongo_db):
    """Test database with schema, indexes, ~600 posts, fake sentiment/topics and all rollups."""
    from app.analytics import rollups
    from app.database.schema import init_database
    from app.ingestion.pipeline import ingest_records

    init_database(mongo_db)
    stats = ingest_records(make_records(), db=mongo_db, profile="generic", source="test", batch_size=100)
    # Stand-in for the NLP step (the trained models are not part of the repository):
    # label English posts by a keyword so the analytics have something to aggregate.
    for word, label, score in (("great", "positive", 0.8), ("terrible", "negative", -0.7)):
        mongo_db.posts.update_many({"language": "en", "clean_text": {"$regex": word}},
                                   {"$set": {"sentiment": {"label": label, "score": score, "confidence": 0.9,
                                                           "method": "test"}}})
    mongo_db.posts.update_many({"language": "en", "sentiment": None},
                               {"$set": {"sentiment": {"label": "neutral", "score": 0.0, "confidence": 0.9,
                                                       "method": "test"}}})
    mongo_db.posts.update_many({}, {"$set": {"processed": True}})
    rollups.build_all(mongo_db)
    return mongo_db, stats


@pytest.fixture(scope="session")
def client(loaded_db):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import cache

    cache.clear()
    with TestClient(app) as c:
        yield c
