"""Train and evaluate sentiment models on TweetEval (sentiment task).

Data: https://github.com/cardiffnlp/tweeteval (datasets/sentiment), 3 classes
(negative / neutral / positive), official train / validation / test split.

Compares:
  * VADER (lexicon baseline, no training)
  * TF-IDF + Multinomial Naive Bayes
  * TF-IDF + Logistic Regression (C chosen on the validation split)

Writes metrics to experiments/results/sentiment_evaluation.json and stores the
best model in backend/models/. Every number in that file comes from this run.
"""
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    recall_score,
)
from sklearn.naive_bayes import MultinomialNB  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.ingestion.cleaning import clean_text  # noqa: E402
from app.nlp.sentiment import TfidfLogRegAnalyzer, VaderAnalyzer, prepare  # noqa: E402

DATA = ROOT / "data" / "raw" / "tweeteval"
LABEL_MAP = {"0": "negative", "1": "neutral", "2": "positive"}


def load(split: str):
    texts = (DATA / f"{split}_text.txt").read_text(encoding="utf-8").splitlines()
    labels = (DATA / f"{split}_labels.txt").read_text(encoding="utf-8").splitlines()
    assert len(texts) == len(labels), split
    # Apply the same cleaning as the ingestion pipeline so train and inference inputs match.
    return [clean_text(t)["clean_text"] for t in texts], [LABEL_MAP[x.strip()] for x in labels]


def metrics(y_true, y_pred, seconds: float, n: int) -> dict:
    labels = ["negative", "neutral", "positive"]
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro"), 4),
        "macro_recall": round(recall_score(y_true, y_pred, average="macro"), 4),
        "per_class": {k: {m: round(v, 4) for m, v in d.items()} for k, d in
                      classification_report(y_true, y_pred, labels=labels, output_dict=True).items() if k in labels},
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
        "inference_seconds": round(seconds, 3),
        "texts_per_second": round(n / seconds, 1) if seconds else None,
    }


def main() -> None:
    xtr, ytr = load("train")
    xva, yva = load("val")
    xte, yte = load("test")
    print(f"train={len(xtr):,} val={len(xva):,} test={len(xte):,}")
    results = {}

    vader = VaderAnalyzer()
    t = time.perf_counter()
    pred = [r["label"] for r in vader.analyze(xte)]
    results["vader"] = metrics(yte, pred, time.perf_counter() - t, len(xte))
    val_f1 = {"vader": f1_score(yva, [r["label"] for r in vader.analyze(xva)], average="macro")}
    print("vader", results["vader"]["macro_f1"])

    t = time.perf_counter()
    nb = Pipeline([("tfidf", TfidfVectorizer(preprocessor=prepare, ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                   ("clf", MultinomialNB(alpha=0.5))]).fit(xtr, ytr)
    nb_train = time.perf_counter() - t
    val_f1["tfidf_nb"] = f1_score(yva, nb.predict(xva), average="macro")
    t = time.perf_counter()
    pred = nb.predict(xte)
    results["tfidf_nb"] = metrics(yte, pred, time.perf_counter() - t, len(xte)) | {"train_seconds": round(nb_train, 2)}
    print("nb", results["tfidf_nb"]["macro_f1"])

    best_c, best_f1, val_scores = None, -1.0, {}
    for c in (0.25, 0.5, 1.0, 2.0, 4.0):
        m = TfidfLogRegAnalyzer.build(C=c).fit(xtr, ytr)
        f1 = f1_score(yva, m.predict(xva), average="macro")
        val_scores[str(c)] = round(f1, 4)
        if f1 > best_f1:
            best_c, best_f1 = c, f1
    t = time.perf_counter()
    lr = TfidfLogRegAnalyzer.build(C=best_c).fit(xtr, ytr)
    lr_train = time.perf_counter() - t
    val_f1["tfidf_logreg"] = best_f1
    t = time.perf_counter()
    pred = lr.predict(xte)
    results["tfidf_logreg"] = metrics(yte, pred, time.perf_counter() - t, len(xte)) | {
        "train_seconds": round(lr_train, 2), "C": best_c, "validation_macro_f1_by_C": val_scores}
    print("logreg", results["tfidf_logreg"]["macro_f1"], "C", best_c)

    # The model family is chosen on the validation split; the test split is only reported.
    for k in results:
        results[k]["validation_macro_f1"] = round(val_f1[k], 4)
    best = max(results, key=lambda k: val_f1[k])
    settings = get_settings()
    lr.save(settings.model_dir / "sentiment_tfidf_logreg.joblib")
    out = {
        "dataset": "TweetEval sentiment (cardiffnlp/tweeteval, official splits)",
        "sizes": {"train": len(xtr), "validation": len(xva), "test": len(xte)},
        "selection_metric": "macro_f1 on the validation split (test split reported only)",
        "best_model": best,
        "results": results,
        "run_at": datetime.now(UTC).isoformat(),
        "hardware": {"platform": platform.platform(), "python": platform.python_version(),
                     "cpu_count": __import__("os").cpu_count()},
    }
    dest = ROOT / "experiments" / "results" / "sentiment_evaluation.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps({k: {m: v[m] for m in ("accuracy", "macro_f1", "macro_recall", "texts_per_second")}
                      for k, v in results.items()}, indent=2))
    print("best:", best, "->", dest)


if __name__ == "__main__":
    main()
