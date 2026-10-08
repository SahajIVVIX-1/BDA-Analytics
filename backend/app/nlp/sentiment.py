"""Sentiment analysers.

Two interchangeable analysers share one interface (`analyze(texts) -> list[dict]`):

* `VaderAnalyzer`  - lexicon/rule-based baseline (no training data needed).
* `TfidfLogRegAnalyzer` - TF-IDF (word 1-2 grams) + multinomial Logistic Regression,
  trained on the TweetEval sentiment benchmark (3 classes, human-annotated tweets).

Both only support English; callers decide what to do with other languages.
Which analyser the pipeline uses is decided by the measured evaluation in
`scripts/train_sentiment.py` (see docs/methodology.md).
"""

from __future__ import annotations

import re
from pathlib import Path

import joblib
import numpy as np

LABELS = ("negative", "neutral", "positive")
_space = re.compile(r"\s+")


def prepare(text: str) -> str:
    """Model input: lower-cased cleaned text (cleaning already removed URLs / mentions)."""
    return _space.sub(" ", (text or "").lower()).strip()


class VaderAnalyzer:
    name = "vader"
    # Standard thresholds recommended by the VADER authors.
    POS, NEG = 0.05, -0.05

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        self._sia = SentimentIntensityAnalyzer()

    def label_from_compound(self, c: float) -> str:
        return "positive" if c >= self.POS else "negative" if c <= self.NEG else "neutral"

    def analyze(self, texts: list[str]) -> list[dict]:
        out = []
        for t in texts:
            s = self._sia.polarity_scores(t or "")
            c = s["compound"]
            out.append({"label": self.label_from_compound(c), "score": round(c, 4),
                        "confidence": round(max(s["pos"], s["neu"], s["neg"]), 4), "method": self.name})
        return out


class TfidfLogRegAnalyzer:
    name = "tfidf_logreg"

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    @classmethod
    def build(cls, C: float = 1.0):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(preprocessor=prepare, ngram_range=(1, 2), min_df=2, max_df=0.9,
                                      sublinear_tf=True, max_features=300_000)),
            ("clf", LogisticRegression(C=C, max_iter=2000, class_weight="balanced")),
        ])
        return cls(pipe)

    def fit(self, texts: list[str], labels: list[str]):
        self.pipeline.fit(texts, labels)
        return self

    def predict(self, texts: list[str]) -> list[str]:
        return list(self.pipeline.predict(texts))

    def analyze(self, texts: list[str]) -> list[dict]:
        proba = self.pipeline.predict_proba(texts)
        classes = list(self.pipeline.classes_)
        ipos, ineg = classes.index("positive"), classes.index("negative")
        best = proba.argmax(axis=1)
        # score in [-1, 1]: P(positive) - P(negative); confidence: probability of the chosen class
        score = proba[:, ipos] - proba[:, ineg]
        conf = proba[np.arange(len(texts)), best]
        return [{"label": classes[b], "score": round(float(s), 4), "confidence": round(float(c), 4),
                 "method": self.name} for b, s, c in zip(best, score, conf, strict=True)]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, path)

    @classmethod
    def load(cls, path: Path):
        return cls(joblib.load(path))


def load_analyzer(method: str, model_dir: Path):
    if method == "vader":
        return VaderAnalyzer()
    if method == "tfidf_logreg":
        path = model_dir / "sentiment_tfidf_logreg.joblib"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found - run scripts/train_sentiment.py first")
        return TfidfLogRegAnalyzer.load(path)
    raise ValueError(f"unknown sentiment method: {method}")
