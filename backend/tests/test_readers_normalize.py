import gzip
import json
from datetime import UTC, datetime

import pytest

from app.ingestion import readers
from app.ingestion.normalize import InvalidRecord, normalize_record

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_detect_format(tmp_path):
    assert readers.detect_format(tmp_path / "a.csv") == "csv"
    assert readers.detect_format(tmp_path / "a.jsonl.gz") == "jsonl"
    assert readers.detect_format(tmp_path / "a.json") == "json"
    with pytest.raises(readers.UnsupportedFormatError):
        readers.detect_format(tmp_path / "a.xlsx")


def test_read_csv_jsonl_json_and_gzip(tmp_path):
    (tmp_path / "a.csv").write_text("id,text\n1,hello\n2,world\n", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text('{"id": 1}\nnot json\n{"id": 2}\n', encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
    with gzip.open(tmp_path / "d.csv.gz", "wt", encoding="utf-8") as f:
        f.write("id,text\n9,zipped\n")
    assert [r["text"] for r in readers.iter_records(tmp_path / "a.csv")] == ["hello", "world"]
    jl = list(readers.iter_records(tmp_path / "b.jsonl"))
    assert len(jl) == 3 and "__parse_error__" in jl[1]  # malformed line is reported, not fatal
    assert len(list(readers.iter_records(tmp_path / "c.json"))) == 2
    assert list(readers.iter_records(tmp_path / "d.csv.gz"))[0]["text"] == "zipped"


def test_expand_paths_natural_sort(tmp_path):
    for n in (10, 2, 1):
        (tmp_path / f"part{n}.csv").write_text("id\n", encoding="utf-8")
    assert [p.name for p in readers.expand_paths([tmp_path])] == ["part1.csv", "part2.csv", "part10.csv"]


def test_normalize_generic_record():
    doc = normalize_record({"id": 42, "text": "Vote today! #Election2016 @bob https://t.co/x",
                            "created_at": "2016-11-08T10:00:00Z", "lang": "English", "country": "Germany",
                            "username": "Alice", "followers": "120", "likes": "3", "replies": 1, "retweets": 2},
                           "generic", "unit", now=NOW)
    assert doc["post_id"] == "42"
    assert doc["language"] == "en"
    assert doc["hashtags"] == ["election2016"] and doc["mentions"] == ["bob"]
    assert doc["location"]["country"] == "Germany"
    assert doc["engagement"] == {"likes": 3, "comments": 1, "shares": 2, "total": 6, "synthetic": False}
    assert doc["processed"] is False and doc["sentiment"] is None


def test_normalize_ira538_record_has_no_engagement():
    doc = normalize_record({"tweet_id": "905", "content": "RT @x: hello there friends", "publish_date": "1/2/2017 10:00",
                            "language": "English", "region": "United States", "author": "ACCT", "followers": "10",
                            "following": "5", "post_type": "RETWEET", "retweet": "1"}, "ira538", "ira", now=NOW)
    assert doc["engagement"] is None
    assert doc["is_retweet"] is True and doc["post_type"] == "retweet"
    assert doc["reach"] == 10


@pytest.mark.parametrize("rec,reason", [
    ({"text": "no id", "created_at": "2016-01-01"}, "missing_id"),
    ({"id": 1, "text": "   ", "created_at": "2016-01-01"}, "empty_text"),
    ({"id": 1, "text": "ok text", "created_at": "garbage"}, "invalid_timestamp"),
    ({"__parse_error__": "bad line"}, "parse_error"),
])
def test_normalize_rejects_invalid(rec, reason):
    with pytest.raises(InvalidRecord) as e:
        normalize_record(rec, "generic", "unit", now=NOW)
    assert e.value.reason == reason
