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

Dataset: **1.23M listening events · 45,000 users · 100 tracks · 4 platforms · full year 2024.**

---

## 🧠 The metrics that matter (and why)

| Metric | What it measures | Why a streaming company cares |
|---|---|---|
| **Discovery Efficiency** | Skip rate by `stream_source` | Algorithmic recommendations skip at **~42%** vs **~22%** for Editorial/Search → the recommender is over-serving mismatched content. |
| **Device experience** | Skip rate by device | Mobile skips **~33%** vs **~28%** on desktop/speaker → where to invest in UX and on-device recommendations. |
| **Monetization** | Revenue & RPM by plan | Revenue per 1,000 active users, split Free vs Premium — is growth adding value or low-value users? |
| **Retention / churn** | Users still active vs churned | Real retention from `churn_date` is **~82%** (18% churn) — *not* the "% who ever listened" a naïve KPI reports. |
| **Seasonality** | Monthly / weekend cycles | Summer and December peaks demand capacity and content planning. |

Full analytical narrative → [`docs/business_questions.md`](docs/business_questions.md)

---

## 🏗️ Architecture

```
Raw events (CSV / generator)
        │
        ▼
  BigQuery raw tables ──► dbt staging (clean, typed, tested)
                                   │
                                   ▼
                         dbt marts (star schema)
              fct_streams · dim_user · dim_track · dim_platform · dim_time
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
             Power BI dashboard             Ad-hoc SQL analysis
             (DAX product metrics)          (sql/analysis/)
```

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
│   └── sample/F_Streams_sample.csv                             # 100k-row sample of the fact table
├── scripts/
│   ├── generate_datasets.py     # reproducible synthetic-data generator (seeded)
│   ├── load_bigquery.py         # load the star schema into BigQuery (+ .sh variant)
│   ├── validate_data.py         # data-quality gate (used in CI)
│   └── make_charts.py           # regenerate the README charts
├── sql/
│   ├── ddl/                     # BigQuery table definitions (star schema)
│   └── analysis/                # the business questions, answered in SQL
├── dbt/streaming/               # staging + marts models with data-quality tests
├── dashboard/
│   └── Music_Stream_Dashboard.pbix   # Power BI report — see docs/dashboard.md
└── docs/
    ├── business_questions.md
    ├── dashboard.md
    └── screenshots/
```

---

## ▶️ Reproduce it

Everything is driven by a `Makefile` (`make help` lists the targets):

```bash
make install          # install Python dependencies
make generate         # regenerate the full 1.23M-row dataset (seeded, deterministic)
make validate         # run the data-quality gate (referential integrity, invariants)
make charts           # rebuild the README charts from the data
```

### Run it on BigQuery

```bash
gcloud auth application-default login
make load PROJECT=your-gcp-project          # Python loader (scripts/load_bigquery.py)
# or:  PROJECT=your-gcp-project ./scripts/load_bigquery.sh   # bq CLI

cd dbt/streaming && dbt deps && dbt build    # build + test the models
```

The full fact table (~1.23M rows) is regenerated by the script and is **not** committed;
a 100k-row sample lives in [`data/sample/`](data/sample/) so the repo is clone-and-run, and
`make load` falls back to that sample automatically if the full file is absent.

**CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) regenerates a small dataset on every
push and runs the data-quality checks, plus a SQL lint (`sqlfluff`, BigQuery dialect).

---

## 🎯 Why this project

I built the data generator to reflect **real streaming-industry dynamics** — circadian listening, weekend and summer lift, algorithmic-vs-editorial discovery, a mobile skip lift, subscription tiers and ~18% churn — so the analysis exercises the same problems a product-analytics team faces. The goal was a portfolio piece that proves I can go from **raw event data → dimensional model → product metrics → decision-ready dashboard**, not just plot a CSV.

**Author:** Matteo Balducci — Data Analyst
[LinkedIn](https://www.linkedin.com/in/matteo-balducci/) · [GitHub](https://github.com/matteobalducci)
