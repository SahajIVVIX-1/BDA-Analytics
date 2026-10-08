"""FastAPI endpoints against the throwaway test database."""

import pytest

from tests.conftest import make_records

pytestmark = pytest.mark.integration
N = len(make_records())


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["mongodb"] is True and body["database"] == "social_analytics_test" and body["posts"] == N


def test_overview(client):
    d = client.get("/api/dashboard/overview").json()
    assert d["total_posts"] == N
    s = d["sentiment"]
    assert s["analysed"] == sum(s["counts"][k] for k in ("positive", "neutral", "negative"))
    assert d["engagement"]["synthetic"] is False  # the test data carries real (fixture) counts


@pytest.mark.parametrize("mode", ["cube", "live"])
def test_cube_and_live_agree(client, mode):
    d = client.get("/api/analytics/sentiment", params={"mode": mode}).json()
    assert sum(d["distribution"]["counts"].values()) == N


def test_filters_narrow_results(client):
    en = client.get("/api/dashboard/overview", params={"language": "en"}).json()["total_posts"]
    ru = client.get("/api/dashboard/overview", params={"language": "ru"}).json()["total_posts"]
    assert en + ru == N and en > ru > 0


def test_invalid_filter_is_422(client):
    assert client.get("/api/analytics/sentiment", params={"sentiment": "angry"}).status_code == 422
    assert client.get("/api/analytics/sentiment", params={"start": "not-a-date"}).status_code == 422


def test_posts_pagination_and_detail(client):
    page = client.get("/api/posts", params={"page_size": 5, "hashtag": "#News"}).json()
    assert len(page["items"]) == 5 and all("news" in p["hashtags"] for p in page["items"])
    pid = page["items"][0]["post_id"]
    assert client.get(f"/api/posts/{pid}").json()["post_id"] == pid
    assert client.get("/api/posts/does-not-exist").status_code == 404


def test_search_uses_text_index(client):
    assert client.get("/api/search").status_code == 422
    res = client.get("/api/search", params={"q": "election"}).json()
    assert res["total"] > 0 and all("election" in p["text"].lower() for p in res["items"])


def test_trends_and_hashtags(client):
    tags = client.get("/api/analytics/hashtags", params={"limit": 10}).json()["items"]
    assert {t["hashtag"] for t in tags} == {"election", "news", "sports", "music"}
    tr = client.get("/api/analytics/trends", params={"kind": "hashtag", "end": "2016-02-15", "min_count": 1}).json()
    assert tr["window"] and isinstance(tr["items"], list)


def test_anomalies_find_the_planted_spike(client):
    d = client.get("/api/analytics/anomalies", params={"min_volume": 1}).json()
    spike = next(a for a in d["anomalies"] if a["day"].startswith("2016-02-15"))  # day 45: 10x the usual volume
    assert "volume_spike" in spike["reasons"]
    # with the default 100-post floor, the z-score rule ignores this small day; IQR still flags it
    d = client.get("/api/analytics/anomalies").json()
    spike = next(a for a in d["anomalies"] if a["day"].startswith("2016-02-15"))
    assert "volume_spike" not in spike["reasons"] and "iqr_outlier" in spike["reasons"]


def test_performance_endpoints(client):
    assert client.get("/api/performance/indexes").status_code == 200
    ex = client.get("/api/performance/explain/hashtag_lookup").json()
    assert ex  # explain output returned


def test_upload_rejects_unsupported_type(client):
    r = client.post("/api/ingestion/upload", files={"file": ("x.exe", b"MZ...", "application/octet-stream")})
    assert r.status_code in (400, 415, 422)
