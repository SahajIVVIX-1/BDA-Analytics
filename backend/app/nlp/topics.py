"""Topic modelling with TF-IDF + NMF (Non-negative Matrix Factorisation).

One model per supported language (English, Russian). Each model holds
  * a TfidfVectorizer (unigrams + bigrams) fitted on a random sample of posts,
  * an NMF decomposition into K topics.

For a document, NMF gives a non-negative weight per topic. The document is
assigned to the topic with the largest weight; if that weight is below
`min_weight` the post is assigned to the language's "other" bucket (the post
uses too little of the modelled vocabulary to be placed reliably).

The same TF-IDF vector also yields per-post keywords: the highest-weighted
terms of that post, which feed keyword trend detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

NLP_DIR = Path(__file__).resolve().parent
SUPPORTED_TOPIC_LANGUAGES = ("en", "ru")

# Domain stop words: tweet boilerplate and high-frequency filler that would otherwise dominate topics.
EXTRA_STOP = {
    "en": {"amp", "rt", "just", "like", "new", "did", "don", "doesn", "get", "got", "say", "says", "said", "via",
           "today", "day", "im", "dont", "know", "people", "time", "make", "want", "need", "think", "going", "good",
           "great", "video", "watch", "read", "2015", "2016", "2017", "u", "ur", "lol", "gonna", "wanna", "i'm",
           "it's", "don't", "that's", "you're", "can't", "let", "really", "right", "way", "thing", "things"},
    "ru": {"это", "rt", "amp", "который", "которые", "также", "очень", "просто", "будет", "году", "года", "ещё",
           "свой", "своих", "своей", "может", "можно", "нужно", "всё", "этой", "этого", "этом"},
}

TOKEN_PATTERNS = {
    "en": r"(?u)\b[a-z][a-z']{2,}\b",
    "ru": r"(?u)\b[а-яё][а-яё\-]{2,}\b",
}


def stop_words(lang: str) -> list[str]:
    if lang == "en":
        base = set(ENGLISH_STOP_WORDS)
    elif lang == "ru":
        base = set((NLP_DIR / "stopwords_ru.txt").read_text(encoding="utf-8").split())
    else:
        base = set()
    return sorted(base | EXTRA_STOP.get(lang, set()))


@dataclass
class TopicModel:
    language: str
    vectorizer: TfidfVectorizer
    nmf: object
    labels: list[str]
    top_terms: list[list[str]]
    min_weight: float = 0.02
    keyword_count: int = 5
    meta: dict = field(default_factory=dict)

    @property
    def k(self) -> int:
        return len(self.labels)

    def topic_id(self, idx: int) -> str:
        return f"{self.language}-{idx:02d}" if idx >= 0 else f"{self.language}-other"

    def transform(self, texts: list[str]) -> list[dict]:
        """Return [{'topic': {...}, 'keywords': [...]}, ...] for a batch of cleaned texts."""
        X = self.vectorizer.transform(texts)
        W = self.nmf.transform(X)
        best = W.argmax(axis=1)
        best_w = W[np.arange(W.shape[0]), best]
        terms = self._terms
        X = X.tocsr()
        out = []
        for i in range(X.shape[0]):
            start, end = X.indptr[i], X.indptr[i + 1]
            idx, vals = X.indices[start:end], X.data[start:end]
            if len(vals) > self.keyword_count:
                top = np.argpartition(-vals, self.keyword_count)[: self.keyword_count]
                top = top[np.argsort(-vals[top])]
            else:
                top = np.argsort(-vals)
            keywords = [terms[idx[j]] for j in top]
            t = int(best[i]) if best_w[i] >= self.min_weight else -1
            out.append({
                "topic": {"id": self.topic_id(t), "label": self.labels[t] if t >= 0 else "Other / unassigned",
                          "weight": round(float(best_w[i]), 4), "method": "tfidf_nmf"},
                "keywords": keywords,
            })
        return out

    @property
    def _terms(self):
        if not hasattr(self, "_terms_cache"):
            self._terms_cache = self.vectorizer.get_feature_names_out()
        return self._terms_cache

    def save(self, model_dir: Path) -> Path:
        model_dir.mkdir(parents=True, exist_ok=True)
        path = model_dir / f"topics_{self.language}.joblib"
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(model_dir: Path, language: str) -> TopicModel:
        return joblib.load(model_dir / f"topics_{language}.joblib")


def auto_label(terms: list[str]) -> str:
    return " / ".join(t.title() if t.isascii() else t for t in terms[:3])


def fit_topic_model(texts: list[str], language: str, k: int, max_features: int = 50_000, min_df: int = 20,
                    random_state: int = 42, label_overrides: dict[int, str] | None = None) -> TopicModel:
    from sklearn.decomposition import NMF

    vec = TfidfVectorizer(lowercase=True, stop_words=stop_words(language), token_pattern=TOKEN_PATTERNS[language],
                          ngram_range=(1, 2), min_df=min_df, max_df=0.3, max_features=max_features, sublinear_tf=True)
    X = vec.fit_transform(texts)
    nmf = NMF(n_components=k, init="nndsvda", random_state=random_state, max_iter=400)
    nmf.fit(X)
    terms = vec.get_feature_names_out()
    top_terms = [[terms[j] for j in comp.argsort()[::-1][:12]] for comp in nmf.components_]
    labels = [auto_label(t) for t in top_terms]
    for i, name in (label_overrides or {}).items():
        labels[i] = name
    return TopicModel(language=language, vectorizer=vec, nmf=nmf, labels=labels, top_terms=top_terms,
                      meta={"sample_size": len(texts), "vocabulary": len(terms), "k": k,
                            "reconstruction_err": float(nmf.reconstruction_err_)})
