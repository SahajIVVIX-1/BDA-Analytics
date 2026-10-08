"""Text cleaning and field normalisation.

Everything here is pure (no I/O) so it can be unit-tested and reused by the
ingestion pipeline, the upload endpoint and the streaming simulator.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import UTC, datetime

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# Twitter handles: 1-15 word chars. Preceded by start or a non-word char so emails don't match.
MENTION_RE = re.compile(r"(?<![\w@])@(\w{1,15})")
# Unicode-aware: hashtags in Cyrillic/Arabic are valid too. Must contain a letter.
HASHTAG_RE = re.compile(r"(?<![\w#&])#(\w*[^\W\d_]\w*)")
RT_PREFIX_RE = re.compile(r"^RT\s+@\w{1,15}:?\s*", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
# Emoji / pictograph ranges (covers the vast majority of emoji in tweets).
EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FAFF"
    "☀-⛿"  # misc symbols
    "✀-➿"  # dingbats
    "]",
    flags=re.UNICODE,
)
VARIATION_RE = re.compile("[\uFE0F\u200D]")
# Control/format characters (Unicode category C*) except tab/newline, removed in one regex pass.
CONTROL_RE = re.compile("[\x00-\x08\x0B-\x1F\x7F-\x9F\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]")
# Fast path for the dataset's "M/D/YYYY H:MM[:SS]" shape (strptime is ~10x slower).
_US_TS_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2})(?::(\d{2}))?$")

# Dataset language names -> ISO 639-1 codes. Unknown names keep a slug so no information is lost.
LANGUAGE_CODES = {
    "english": "en", "russian": "ru", "german": "de", "ukrainian": "uk", "italian": "it",
    "serbian": "sr", "uzbek": "uz", "bulgarian": "bg", "arabic": "ar", "macedonian": "mk",
    "french": "fr", "spanish": "es", "norwegian": "no", "farsi (persian)": "fa", "persian": "fa",
    "dutch": "nl", "swedish": "sv", "romanian": "ro", "japanese": "ja", "estonian": "et",
    "croatian": "hr", "portuguese": "pt", "polish": "pl", "finnish": "fi", "lithuanian": "lt",
    "hungarian": "hu", "turkish": "tr", "czech": "cs", "albanian": "sq", "kazakh": "kk",
    "latvian": "lv", "hebrew": "he", "chinese": "zh", "korean": "ko", "greek": "el",
    "vietnamese": "vi", "slovak": "sk", "slovenian": "sl", "danish": "da", "icelandic": "is",
    "hindi": "hi", "pushto": "ps", "pashto": "ps", "urdu": "ur", "tagalog": "tl", "malay": "ms",
    "indonesian": "id", "thai": "th", "somali": "so", "bosnian": "bs", "catalan": "ca",
    "belarusian": "be", "georgian": "ka", "armenian": "hy", "azerbaijani": "az", "kurdish": "ku",
    "en": "en", "ru": "ru", "de": "de",
}
UNKNOWN_LANGUAGE_VALUES = {"", "language undefined", "und", "unknown", "none", "null", "nan"}
UNKNOWN_LOCATION_VALUES = {"", "unknown", "none", "null", "nan", "n/a"}

TIMESTAMP_FORMATS = (
    "%m/%d/%Y %H:%M",       # FiveThirtyEight IRA dataset
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%a %b %d %H:%M:%S %z %Y",  # Twitter API v1 created_at
    "%a %b %d %H:%M:%S PDT %Y",  # Sentiment140
    "%Y-%m-%d",
)
# Platform sanity window: anything outside is treated as an invalid timestamp.
MIN_VALID_TS = datetime(2006, 3, 21, tzinfo=UTC)  # first ever tweet


def _parse_timestamp_string(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_timestamp(value, now: datetime | None = None) -> datetime | None:
    """Parse many timestamp shapes to an aware UTC datetime. Returns None if invalid.

    Naive timestamps are assumed to be UTC (documented assumption for the source dataset).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            # Accept seconds or milliseconds since epoch.
            dt = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        s = str(value).strip()
        if not s:
            return None
        dt = None
        m = _US_TS_RE.match(s)
        if m:
            mo, d, y, hh, mm, ss = m.groups()
            try:
                dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0))
            except ValueError:
                return None
        else:
            dt = _parse_timestamp_string(s)
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    now = now or datetime.now(UTC)
    if dt < MIN_VALID_TS or dt > now:
        return None
    return dt


def normalize_language(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in UNKNOWN_LANGUAGE_VALUES:
        return None
    if s in LANGUAGE_CODES:
        return LANGUAGE_CODES[s]
    if len(s) == 2 and s.isalpha():
        return s
    return re.sub(r"[^a-z]+", "_", s).strip("_") or None


def normalize_location(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in UNKNOWN_LOCATION_VALUES:
        return None
    return s


def to_non_negative_int(value) -> int | None:
    if value is None:
        return None
    try:
        n = int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None
    return n if n >= 0 else None


def extract_hashtags(text: str) -> list[str]:
    """Lower-cased, de-duplicated hashtags (order preserved), without '#'."""
    seen: dict[str, None] = {}
    for tag in HASHTAG_RE.findall(text):
        seen.setdefault(tag.lower(), None)
    return list(seen)


def extract_mentions(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in MENTION_RE.findall(text):
        seen.setdefault(m.lower(), None)
    return list(seen)


def clean_text(raw: str) -> dict:
    """Return the cleaned text plus the entities extracted from it.

    Cleaning steps (in order):
      1. HTML-unescape (&amp; -> &) and Unicode NFC normalisation
      2. extract hashtags / mentions / URLs / emoji from the original text
      3. drop the leading "RT @user:" retweet prefix
      4. remove URLs and mentions, keep hashtag words (strip '#') because they carry meaning
      5. remove emoji and control characters, collapse whitespace
    """
    text = unicodedata.normalize("NFC", html.unescape(raw or ""))
    hashtags = extract_hashtags(text)
    mentions = extract_mentions(text)
    urls = URL_RE.findall(text)
    emojis = EMOJI_RE.findall(text)

    is_rt = bool(RT_PREFIX_RE.match(text))
    body = RT_PREFIX_RE.sub("", text)
    body = URL_RE.sub(" ", body)
    body = MENTION_RE.sub(" ", body)
    body = re.sub(r"#(\w)", r"\1", body)
    body = EMOJI_RE.sub(" ", body)
    body = VARIATION_RE.sub("", body)
    body = CONTROL_RE.sub("", body)
    body = WHITESPACE_RE.sub(" ", body).strip()

    return {
        "clean_text": body,
        "hashtags": hashtags,
        "mentions": mentions,
        "url_count": len(urls),
        "emojis": sorted(set(emojis)),
        "rt_prefix": is_rt,
    }


def text_fingerprint(clean: str) -> str:
    """Hash of the normalised text, used to detect copy-paste duplicates across accounts."""
    norm = re.sub(r"[^\w\s]", "", clean.lower())
    norm = WHITESPACE_RE.sub(" ", norm).strip()
    return hashlib.blake2b(norm.encode("utf-8"), digest_size=12).hexdigest()


def quality_flags(clean: str, hashtags: list[str], mentions: list[str], url_count: int) -> list[str]:
    """Heuristic noise / spam-like flags. Flagged posts are kept (and can be filtered out)."""
    flags = []
    words = clean.split()
    if len(words) < 3:
        flags.append("short_text")
    if len(hashtags) >= 5:
        flags.append("hashtag_stuffing")
    if len(mentions) >= 5:
        flags.append("mention_stuffing")
    if url_count >= 1 and len(words) < 4:
        flags.append("link_only")
    if words and len(set(w.lower() for w in words)) / len(words) < 0.4 and len(words) >= 6:
        flags.append("repetitive")
    return flags
