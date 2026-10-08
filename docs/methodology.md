# Methodology

How each analytic number is produced, what it assumes, and where it is weak. Measured results are in
[performance.md](performance.md); this document explains the methods.

## 1. Text cleaning

Applied once at ingestion (`backend/app/ingestion/cleaning.py`), in this order:

1. HTML entities unescaped (`&amp;` -> `&`), Unicode NFC normalisation.
2. Hashtags, mentions, URLs and emoji extracted from the original text. Hashtags and mentions are lower-cased
   and de-duplicated; the hashtag pattern accepts any Unicode letters, so `#Москва` works.
3. A leading `RT @user:` is removed and recorded.
4. URLs and mentions removed; hashtag words kept without `#` because they carry meaning ("#MAGA" -> "MAGA").
5. Emoji, variation selectors and control characters removed; whitespace collapsed.

Timestamps: the IRA format `M/D/YYYY H:MM` is parsed by a fast regular expression; other formats (ISO 8601,
epoch seconds or milliseconds) by a fallback parser. Timestamps without a zone are **assumed to be UTC**, which
the source does not confirm. Dates before 2006-03-21 (Twitter's launch) or in the future are rejected.

Quality flags (kept, not deleted): `short_text` (< 3 words), `link_only` (a URL and < 4 words),
`hashtag_stuffing` (>= 5 hashtags), `mention_stuffing` (>= 5 mentions), `repetitive` (>= 6 words, < 40% unique),
`no_text_content` (nothing left after cleaning). The thresholds are heuristics chosen for this project, not taken
from a published standard.

Duplicates: a unique index on `post_id` rejects repeated ids. Identical *texts* from different ids are kept
(they are part of the copy-paste behaviour the dataset documents) and grouped with `text_hash`, a 12-byte BLAKE2b
hash of the lower-cased text with punctuation removed.

## 2. Sentiment

**Task.** Three classes (negative, neutral, positive) for English posts.

**Models compared** (`scripts/train_sentiment.py`, all trained on the TweetEval training split):

| Model | Description |
| --- | --- |
| VADER | Rule-based lexicon (vaderSentiment 3.3.2), compound score >= 0.05 positive, <= -0.05 negative, otherwise neutral (thresholds from the VADER documentation). Not trained |
| TF-IDF + Multinomial Naive Bayes | word 1-2 grams, `alpha = 0.5` |
| TF-IDF + Logistic Regression | word 1-2 grams, `min_df = 2`, `max_df = 0.9`, sublinear TF, up to 300,000 features, `class_weight = balanced`; `C` chosen from {0.25, 0.5, 1, 2, 4} by validation macro-F1 |

**Selection.** The model family is chosen by **macro-F1 on the validation split**; the test split is used only
to report the final scores. Macro-F1 is used instead of accuracy because the classes are imbalanced (the test
split is 48% neutral).

**Result.** TF-IDF + logistic regression was selected. Its test scores and those of the alternatives are in
[performance.md, section 8](performance.md#8-sentiment-model-evaluation).

For context, TweetEval's official metric for this task (following SemEval-2017 Task 4A) is macro-averaged
recall. On that metric the selected model scores 59.3 (x100) on the test split. The TweetEval repository's
leaderboard (reported there, not reproduced here) lists 62.9 for its SVM and FastText baselines, 71.3 for
RoBERTa-base and 73.4 for BERTweet. So this model is a few points below simple published baselines and well below
transformer models, which this project does not use because of the CPU-only constraint. Improving it is listed as
future work.

**Stored per post.** `label`, `score = P(positive) - P(negative)` in [-1, 1], `confidence = max class
probability`, `method`.

**Limitations.**

* Domain shift: TweetEval contains general tweets, the IRA data is propaganda and news-style text. Accuracy on
  the IRA tweets is **not measured** (they have no labels).
* Sarcasm, irony and context outside the tweet are not modelled.
* Non-English posts (28% of the data) get no sentiment and are reported as `not_analyzed`.

## 3. Topics

**Method.** Non-negative matrix factorisation of TF-IDF matrices, one model per language
(`backend/app/nlp/topics.py`, `scripts/train_topics.py`):

* Training sample: 200,000 random posts per language (`$sample`), English and Russian.
* TF-IDF: 1-2 grams, letters-only tokens of 3+ characters, English stop words from scikit-learn plus a project
  list of filler words and retweet artefacts (`rt`, `amp`, `via`, `just`, `like`, years, ...); Russian stop words from the NLTK list; `min_df = 20`, `max_df = 0.3`,
  up to 50,000 features.
* NMF: `k = 16` (English) and `k = 12` (Russian), `init = nndsvda`, `random_state = 42`, `max_iter = 400`.
  The values of `k` were chosen by inspecting the resulting term lists for readability; they were **not tuned**
  with a coherence metric.
* Labels: the top three terms of each component ("Trump / Donald / Donald Trump"); the full top-12 list is
  stored in the `topics` collection and shown in the dashboard.

**Assignment.** Each post gets the component with the largest weight, if that weight is at least 0.02; otherwise
it is `en-other` / `ru-other` ("Other / unassigned"). With this threshold **66% of English posts and 75% of
Russian posts are unassigned**: most tweets are short and do not load strongly on any one component. Topic charts
in the dashboard therefore cover the assigned minority, and pages say so.

**Keywords.** The (up to) five highest-weighted TF-IDF terms of each post, from the same vectoriser. They feed
keyword trends.

**Topic growth** is the trend method below applied to topic counts in 30-day windows.

## 4. Trends

For an item (hashtag, keyword or topic), an end date `E` and a window length `w` days:

* `current` = posts in `(E - w, E]`, `previous` = posts in `(E - 2w, E - w]` (from `hashtag_daily`,
  `keyword_daily` or `daily_cube`).
* `growth_pct = (current - previous) / max(previous, 1) x 100`
* `trend_score = log10(1 + current) x log2((current + 5) / (previous + 5)) x (1 + 0.1 x log10(1 + avg_reach))`
* `share_growth_pct` = change in the item's share of **all** posts between the windows.

Reasoning: `log2` of the smoothed ratio rewards growth symmetrically (doubling = +1, halving = -1); the `+5`
additive smoothing stops "0 -> 3 mentions" from looking like infinite growth; `log10(1 + current)` favours items
with real volume; the reach term is a small bonus for items posted by larger accounts. Items need
`current >= min_count` (20 hashtag posts by default) to be ranked. The constants (5, 0.1, the minimum counts) are
design choices for this project, not values from the literature.

**Volume warning.** When total volume differs by more than 3x between the two windows (for example around a
data collection gap), raw growth mostly reflects the data collection, so the API returns a warning and the
dashboard switches to share growth.

**Default end date.** "Latest" windows end at the 99th percentile of post dates (2017-11-13) rather than the last
post, because the last months are a sparse tail.

## 5. Anomalies

Computed on the daily series of posts (`backend/app/analytics/anomalies.py`); filters apply, so anomalies can be
found for one language, topic or country.

| Method | Definition |
| --- | --- |
| Rolling z-score (volume) | `z = (posts_today - mean) / std` over the **28 previous days** (not including today), computed in MongoDB with `$setWindowFields`; needs at least 14 days of history; flagged when `\|z\| >= 3` (adjustable) |
| Rolling z-score (negativity) | same on the share of negative posts among analysed posts |
| Minimum volume | z-score rules only apply when the day or its expected value has at least 100 posts, so 2 -> 12 posts in the sparse early years is not a "spike" |
| IQR | flagged when daily posts are outside `[Q1 - 1.5 IQR, Q3 + 1.5 IQR]` of the whole selected period |
| Isolation Forest | scikit-learn, 200 trees, `contamination = 0.02`, `random_state = 42`; features: log posts, negative share, retweet share, log mean reach |

Days are ranked by how many methods agree, then by `|z|`. The methods answer different questions: the rolling
z-score finds departures from the recent past, IQR finds globally extreme days, Isolation Forest finds unusual
combinations of features. None of them says *why* a day is unusual; the Data Explorer is used for that.

Known effects: IQR on a series that grows over years flags most busy days of the busy years; Isolation Forest
always flags about 2% of days by construction (`contamination`).

## 6. Synthetic engagement

The dataset has no engagement counts. `scripts/synthesize_engagement.py` creates them so the engagement module
can be exercised end to end:

```
rng      = numpy PCG64, seeded with blake2b(post_id) XOR 20261008   (deterministic per post)
base     = 0.004 x followers^0.85, x 0.1 for retweets
likes    = floor(base x LogNormal(0, 1.1))
shares   = Binomial(likes, Uniform(0.10, 0.35))
comments = Binomial(likes, Uniform(0.02, 0.12))
total    = likes + comments + shares
```

The constants were chosen to give plausible-looking magnitudes; they are **not fitted to real Twitter data**.
Every value is marked `synthetic: true` and shown with a badge. Because the generator ignores content, any
pattern in "engagement by sentiment / topic / time" reflects only which accounts posted, never audience
reaction. Engagement rate is defined as `engagement / reach x 1000` (per 1,000 followers).

## 7. Aggregation correctness

The cube and live paths must give the same answers. `backend/tests/test_api.py::test_cube_and_live_agree` checks
this for the sentiment page on test data. The cube uses `$ifNull` defaults (`unknown` language, `Unknown`
country, `not_analyzed` sentiment, `none` topic) that the live path mirrors.

## 8. Timing methodology (experiments)

* Each measurement is repeated (`--runs`, default 3) and the **median** is reported, with all runs kept in the
  JSON.
* Index experiments use MongoDB's own `executionTimeMillis` from `explain("executionStats")` and force the
  collection scan with `hint({$natural: 1})`.
* Aggregation and NLP experiments use wall-clock time around the full Python call.
* Data subsets (100K, 500K, 1M) are the first N posts in ingestion order, copied server-side into separate
  databases with `$out`, so the full dataset is untouched.
* Collections are warm in the WiredTiger cache (4 GB in the measurements here); cold-cache timings would be
  slower and were not measured.
* Hardware, OS, Python and MongoDB versions are recorded with every result.
