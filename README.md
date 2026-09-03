# 🎧 Music Streaming Analytics — Product Analytics for a Streaming Platform

[![CI](https://github.com/matteobalducci/music-streaming-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/matteobalducci/music-streaming-analytics/actions/workflows/ci.yml)

An end-to-end analytics project that models the **digital twin of a music streaming service** (Spotify / Apple Music / YouTube Music style) and answers the question every streaming company cares about:

> *"How do our users consume music, and how do we optimize their experience to grow retention and revenue?"*

This is not a "count the streams" dashboard. It measures **stream quality, discovery efficiency, monetization and retention** — the metrics product and content teams at streaming platforms actually use.

**Stack:** Python (pandas, NumPy) · dimensional modeling (star schema) · SQL / BigQuery · dbt · Power BI

---

## 📊 What the data shows

<table>
<tr>
<td width="50%"><img src="docs/screenshots/skip_rate_by_source.png" alt="Skip rate by source"/></td>
<td width="50%"><img src="docs/screenshots/skip_rate_by_device.png" alt="Skip rate by device"/></td>
</tr>
<tr>
<td width="50%"><img src="docs/screenshots/monthly_seasonality.png" alt="Monthly seasonality"/></td>
<td width="50%"><img src="docs/screenshots/subscription_mix.png" alt="Subscription mix"/></td>
</tr>
</table>

Dataset: **1.22M listening events · 45,000 users · 100 tracks · 4 platforms · full year 2024.**

The dataset is synthetic and **seeded**: `make generate` reproduces it, and
[`tests/test_headline_metrics.py`](tests/test_headline_metrics.py) asserts that the
figures quoted below still come out of it. They are findings, so they are covered by
CI rather than left to drift.

---

## 🧠 The metrics that matter (and why)

| Metric | What it measures | Why a streaming company cares |
|---|---|---|
| **Discovery Efficiency** | Skip rate by `stream_source` | Algorithmic recommendations skip at **~42%** vs **~22%** for Editorial/Search → the recommender is over-serving mismatched content. |
| **Device experience** | Skip rate by device | Mobile skips **~33%** vs **~28%** on desktop/speaker → where to invest in UX and on-device recommendations. |
| **Monetization** | Revenue & RPM by plan | Premium is 55% of users but **82%** of revenue; Free monetises at ~a quarter the rate per stream. |
| **Retention / churn** | Users still active vs churned | Real retention from `churn_date` is **~82%** (18% churn) — *not* the **~96%** "% who ever listened" a naïve KPI reports. |
| **Seasonality** | Monthly / weekend cycles | Raw volume tracks user growth, not season. Per active user: summer **+16%**, December **+11%**, February **−19%**, weekends **+25%**. |

Full analytical narrative → [`docs/business_questions.md`](docs/business_questions.md)

---

## 🏗️ Architecture

```
Raw events (CSV / generator)
        │
        ▼
  BigQuery raw tables (F_Streams · dim_user · dim_track · dim_platform · dim_time)
        │
        ├──────────────────────────────┐
        ▼                              ▼
  Power BI dashboard             dbt staging (clean, typed, tested)
  (DAX product metrics,                │
   reads the raw tables directly)      ▼
                              dbt marts (fct_streams + 3 analytics marts)
                                        │
                                        ▼
                              Ad-hoc SQL analysis (sql/analysis/)
```

The four dimensions load straight into their final star-schema names — no dbt
model rebuilds them, so they're **sources**, not marts (see
[`dbt/streaming/models/staging/_sources.yml`](dbt/streaming/models/staging/_sources.yml)).
`fct_streams` is the one table dbt actually builds, enriching the raw `F_Streams`
landing table with `completion_ratio` and `is_engaged_stream`. Power BI is the left
branch: it connects to the raw load directly, before dbt runs — see
[`docs/dashboard.md`](docs/dashboard.md) for why. The right branch is where dbt's
tested, typed layer earns its keep: SQL analysis and any tool that wants one
denormalised table read `fct_streams` and the three analytics marts
(`mart_discovery_efficiency`, `mart_streaming_flat`, `mart_user_retention`) instead.

**Dimensional model (star schema — 1 fact + 4 dimensions):**

- `fct_streams` — one row per listening event (device, source, skip/like, revenue)
- `dim_user` — country, subscription plan, signup channel, **churn_date** (retention)
- `dim_track` — genre, audio features (energy, valence, danceability, bpm)
- `dim_platform` — Spotify / Apple Music / YouTube Music / SoundCloud
- `dim_time` — calendar with weekend/seasonality flags

---

## 📁 Repository structure

```
music-streaming-analytics/
├── data/
│   ├── D_Users.csv  D_Tracks.csv  D_Platform.csv  D_Time.csv   # dimensions (full)
│   └── sample/F_Streams_sample.csv                             # 4,000 whole users (~112k rows) of the fact
├── scripts/
│   ├── generate_datasets.py     # reproducible synthetic-data generator (seeded)
│   ├── load_bigquery.py         # load the star schema into BigQuery (+ .sh variant)
│   ├── check_dbt_target.py      # `make deploy` guard: PROJECT/DATASET must match the dbt profile
│   ├── validate_data.py         # data-quality gate (used in CI)
│   ├── make_sample.py           # rebuild data/sample/F_Streams_sample.csv
│   └── make_charts.py           # regenerate the README charts
├── sql/
│   ├── ddl/                     # BigQuery table definitions (star schema)
│   └── analysis/                # the business questions, answered in SQL
├── dbt/streaming/               # staging + marts models with data-quality tests
├── tests/
│   ├── test_headline_metrics.py       # asserts the generator produces the documented figures
│   ├── test_business_questions_sql.py # executes sql/analysis/ (via DuckDB) and checks the output
│   └── conftest.py                    # the DuckDB/sqlglot runner behind the test above
├── dashboard/
│   └── Music_Stream_Dashboard.pbix   # Power BI report — see docs/dashboard.md
└── docs/
    ├── business_questions.md
    ├── dashboard.md
    ├── gcp_setup_notes.md
    └── screenshots/
```

---

## ▶️ Reproduce it

Everything is driven by a `Makefile` (`make help` lists the targets):

```bash
make install          # install core Python dependencies — no cloud needed for any of this
make generate         # regenerate the full 1.22M-row dataset (seeded, deterministic)
make sample           # rebuild the committed ~112k-row public sample (whole users)
make validate         # run the data-quality gate on the full table and the sample
make test             # assert the README's headline figures, and the SQL that produces them
make charts           # rebuild the README charts from the data
make all              # generate + sample + validate + test, no cloud needed
```

`make install` deliberately does **not** pull in `google-cloud-bigquery` or `dbt-bigquery`
— either one drags in `grpcio`, which can trigger the slow source build described below,
and nothing in the local path above touches BigQuery or dbt.

### Run it on BigQuery

```bash
gcloud auth application-default login
make install-dbt      # google-cloud-bigquery + dbt-bigquery, kept out of the local-only install above
cp dbt/streaming/profiles.example.yml ~/.dbt/profiles.yml   # fill in your project

make deploy PROJECT=your-gcp-project   # load, then build + test the dbt models
```

`deploy` checks *before* loading anything that `PROJECT`/`DATASET` actually match
what `~/.dbt/profiles.yml` will build against — the loader and `dbt build` read their
target from two different places, and without that check they can silently diverge
(load one project, build another). Running `make load` and `dbt build` as separate
steps skips that check; only reach for that if you're intentionally doing something
`deploy` doesn't support, e.g. `PROJECT=your-gcp-project ./scripts/load_bigquery.sh`
(bq CLI variant) followed by `cd dbt/streaming && dbt deps && dbt build`.

> Setting up on a fresh, no-billing GCP project? See
> [`docs/gcp_setup_notes.md`](docs/gcp_setup_notes.md) — a date-partitioned load
> silently writes zero rows without billing linked. Until billing is linked, pass
> `--no-partition` to `load_bigquery.py` (or `NO_PARTITION=1` to `load_bigquery.sh`).
> `pip install` may also fall back to a slow source build of `grpcio` on some Intel Mac
> setups. Both have quick fixes.

The **full, real fact table** (1.22M rows, ~102 MB — regenerated from the same seeded
generator behind the Power BI dashboard, though the shipped `.pbix` still holds an
earlier cached load about 1% off from what the repo produces today; see
[`docs/dashboard.md`](docs/dashboard.md) for the exact reconciliation) is published as a
[**GitHub Release asset**](../../releases) rather than committed to git history, so the
repo stays clone-and-run. A ~112k-row real sample lives
in [`data/sample/`](data/sample/) for development, CI, and `make load` (which falls back
to it automatically if the full file is absent). That sample is rebuilt by `make sample`
and drawn by **whole user**, never by row: a random slice of rows would leave every
sampled user missing most of their history, quietly breaking retention, active-user and
per-user revenue on the very file most people open first. Alternatively, `make generate`
produces a statistically-similar *synthetic* dataset from the seeded generator.

**CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs on every push: regenerates a
small dataset and runs the data-quality gate on it *and* on the committed sample
(`data-quality`); executes the SQL from `sql/analysis/` against DuckDB and asserts it
reproduces every documented figure (`headline-metrics`); lints all SQL, blocking on
failure (`lint-sql`); and parses the whole dbt project — resolving every `ref`/`source`/
macro with no live BigQuery connection — to catch a broken model before it reaches a real
`dbt build` (`dbt-compile`).

---

## 🎯 Why this project

I built the data generator to reflect **real streaming-industry dynamics** — seasonality (summer & December lift), weekend lift, algorithmic-vs-editorial discovery, a mobile skip lift, subscription tiers and ~18% churn — so the analysis exercises the same problems a product-analytics team faces. The goal was a portfolio piece that proves I can go from **raw event data → dimensional model → product metrics → decision-ready dashboard**, not just plot a CSV.

**Author:** Matteo Balducci — Data Analyst
[LinkedIn](https://www.linkedin.com/in/matteo-balducci/) · [GitHub](https://github.com/matteobalducci)
