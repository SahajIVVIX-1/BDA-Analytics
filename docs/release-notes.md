Data lake snapshot built by `python -m bigdata.spark.pipeline` from the FiveThirtyEight russian-troll-tweets
dataset (CC BY 4.0).

* `lake-silver.zip`: cleaned, de-duplicated posts as Parquet, partitioned by year/month (2,944,519 rows)
* `lake-gold.zip`: five aggregate tables (daily activity, hashtags per day, top hashtags, accounts, monthly categories)
* `experiment-results.zip`: every measured result in `experiments/results/`

Restore by unzipping in the project root: the files land in `data/lake/` and `experiments/results/`.
See docs/bigdata.md for how they were built and measured.
