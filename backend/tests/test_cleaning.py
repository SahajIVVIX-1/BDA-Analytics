from datetime import UTC, datetime

from app.ingestion import cleaning as c

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_parse_timestamp_formats():
    assert c.parse_timestamp("10/1/2017 19:58", NOW) == datetime(2017, 10, 1, 19, 58, tzinfo=UTC)
    assert c.parse_timestamp("2016-11-08T12:00:00Z", NOW) == datetime(2016, 11, 8, 12, tzinfo=UTC)
    assert c.parse_timestamp("2016-11-08T14:00:00+02:00", NOW) == datetime(2016, 11, 8, 12, tzinfo=UTC)
    assert c.parse_timestamp(1478606400, NOW) == datetime(2016, 11, 8, 12, tzinfo=UTC)
    assert c.parse_timestamp(1478606400000, NOW) == datetime(2016, 11, 8, 12, tzinfo=UTC)


def test_parse_timestamp_rejects_invalid_and_out_of_range():
    assert c.parse_timestamp(None, NOW) is None
    assert c.parse_timestamp("", NOW) is None
    assert c.parse_timestamp("not a date", NOW) is None
    assert c.parse_timestamp("13/45/2017 10:00", NOW) is None
    assert c.parse_timestamp("2001-01-01T00:00:00Z", NOW) is None  # before Twitter existed
    assert c.parse_timestamp("2030-01-01T00:00:00Z", NOW) is None  # in the future


def test_clean_text_extracts_entities_and_strips_noise():
    out = c.clean_text("RT @Someone: Big rally &amp; #MAGA #maga today @CNN https://t.co/abc 🇺🇸🔥")
    assert out["rt_prefix"] is True
    assert out["hashtags"] == ["maga"]
    assert "cnn" in out["mentions"] and "someone" in out["mentions"]
    assert out["url_count"] == 1
    assert out["emojis"]
    assert out["clean_text"] == "Big rally & MAGA maga today"


def test_unicode_hashtags_are_kept():
    assert c.extract_hashtags("Привет #Москва и #новости") == ["москва", "новости"]


def test_language_and_location_normalisation():
    assert c.normalize_language("English") == "en"
    assert c.normalize_language("RU") == "ru"
    assert c.normalize_language("LANGUAGE UNDEFINED") is None
    assert c.normalize_location("Unknown") is None
    assert c.normalize_location(" United States ") == "United States"


def test_to_non_negative_int():
    assert c.to_non_negative_int("12") == 12
    assert c.to_non_negative_int("3.0") == 3
    assert c.to_non_negative_int("-1") is None
    assert c.to_non_negative_int("abc") is None


def test_fingerprint_ignores_case_and_punctuation():
    assert c.text_fingerprint("Hello, World!") == c.text_fingerprint("hello world")
    assert c.text_fingerprint("hello world") != c.text_fingerprint("hello there")


def test_quality_flags():
    assert "short_text" in c.quality_flags("hi", [], [], 0)
    assert "hashtag_stuffing" in c.quality_flags("a b c d", list("abcde"), [], 0)
    assert "link_only" in c.quality_flags("look", [], [], 1)
    assert c.quality_flags("a perfectly normal sentence here", [], [], 0) == []
