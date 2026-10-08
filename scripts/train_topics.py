"""Fit the TF-IDF + NMF topic models from a random sample of posts stored in MongoDB.

The sample is drawn server-side with the `$sample` aggregation stage, so only
the sampled texts ever reach Python (memory stays bounded for any collection size).

  python scripts/train_topics.py                 # en (k=16) and ru (k=12)
  python scripts/train_topics.py --sample 100000 --k-en 20
"""
import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.database import mongo  # noqa: E402
from app.nlp.topics import fit_topic_model  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200_000, help="posts sampled per language")
    ap.add_argument("--k-en", type=int, default=16)
    ap.add_argument("--k-ru", type=int, default=12)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    db = mongo.get_db(args.db)
    settings = get_settings()
    report = {"run_at": datetime.now(UTC).isoformat(), "models": {}}
    for lang, k in (("en", args.k_en), ("ru", args.k_ru)):
        t0 = time.perf_counter()
        texts = [d["clean_text"] for d in db.posts.aggregate([
            {"$match": {"language": lang, "clean_text": {"$ne": ""}}},
            {"$sample": {"size": args.sample}},
            {"$project": {"_id": 0, "clean_text": 1}},
        ], allowDiskUse=True)]
        t_sample = time.perf_counter() - t0
        if len(texts) < 1000:
            print(f"{lang}: only {len(texts)} posts, skipped")
            continue
        t1 = time.perf_counter()
        model = fit_topic_model(texts, lang, k, min_df=10 if lang == "ru" else 20)
        t_fit = time.perf_counter() - t1
        model.save(settings.model_dir)
        print(f"\n[{lang}] sample={len(texts):,} sample_time={t_sample:.1f}s fit_time={t_fit:.1f}s")
        db[mongo.TOPICS].delete_many({"language": lang})
        docs = []
        for i, (label, terms) in enumerate(zip(model.labels, model.top_terms, strict=True)):
            print(f"  {model.topic_id(i)}  {', '.join(terms[:8])}")
            docs.append({"_id": model.topic_id(i), "language": lang, "label": label, "top_terms": terms,
                         "method": "tfidf_nmf", "trained_at": datetime.now(UTC)})
        docs.append({"_id": model.topic_id(-1), "language": lang, "label": "Other / unassigned", "top_terms": [],
                     "method": "tfidf_nmf", "trained_at": datetime.now(UTC)})
        db[mongo.TOPICS].insert_many(docs)
        report["models"][lang] = {**model.meta, "sample_seconds": round(t_sample, 2), "fit_seconds": round(t_fit, 2),
                                  "topics": [{"id": model.topic_id(i), "label": lbl, "top_terms": tt}
                                             for i, (lbl, tt) in enumerate(zip(model.labels, model.top_terms, strict=True))]}
    dest = ROOT / "experiments" / "results" / "topic_model.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("->", dest)


if __name__ == "__main__":
    main()
