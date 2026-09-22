# Looker Studio dashboard — contents

**[Open the live report →](https://lookerstudio.google.com/reporting/00845386-7ca0-4cbd-9e5e-96ec0d42c012)** — fully interactive, no download or account needed.

This is the Google-stack companion to the [Power BI dashboard](dashboard.md) — same
underlying data, same findings, different tool and (crucially) a different data path.

**Built on two dbt marts made specifically for it.** Looker Studio doesn't model a
star schema with joins as well as Power BI does, so instead of connecting to the raw
`F_Streams` + dimension tables, this report reads two wide, pre-flattened marts from
`dbt/streaming/models/marts/`:
- **`mart_streaming_flat`** — one row per listening event, every dimension (device,
  source, genre, plan, country, calendar) already joined in.
- **`mart_user_retention`** — one row per user, for retention and active-user metrics
  (a different grain, kept deliberately separate).

**Live data, not a frozen snapshot.** The Power BI `.pbix` was built once from data
loaded into BigQuery at the time and ships with that snapshot embedded. This report
queries `matteo-streaming-analytics.streaming` directly on every load, so its numbers
always reflect whatever is currently in BigQuery — which is exactly the **"Regenerated
(authoritative)"** column in [`docs/dashboard.md`](dashboard.md#data-verified), not the
frozen numbers in the shipped `.pbix`. The two dashboards are expected to differ by
the same ~1% documented there, and they do (see below).

## Pages (5)

| # | Page | Contents |
|---|---|---|
| 1 | **Growth & Monetization** | 3 scorecards (Total Active Users, RPM, Retention Rate %), monthly active-users trend by plan (line), Free/Premium mix (donut) |
| 2 | **Engagement** | Skip Rate % by device (bar), streams by genre (table), streams by country (geo map) |
| 3 | **Financials** | 3 scorecards (Total Revenue, RPM, Gross Margin %), monthly revenue trend (line), revenue by plan (bar) |
| 4 | **Key Drivers** | Skip Rate % by `stream_source` (bar) — Looker Studio has no native equivalent of Power BI's Key Influencers / Decomposition Tree, so this page shows the raw driver data instead and cites the [skip-prediction model](https://github.com/matteobalducci/streaming-insights-copilot) as independent confirmation |
| 5 | **Seasonality & Behavior** | Streams per Active User by month (bar, seasonality shape), Avg Streams per Day — weekend vs. weekday (bar), Like Rate % by genre (bar). This page has **no Power BI equivalent** — it surfaces a finding (`docs/business_questions.md` Q5/Q9/Q10, seasonality and weekend lift) that was previously documented in SQL/prose only and never actually charted in either dashboard, plus the `Like Rate %` metric, which existed as a calculated field but wasn't attached to any visual until now |

## Calculated fields

| Field | Formula | Source |
|---|---|---|
| Retention Rate % | `COUNT_DISTINCT(CASE WHEN churn_date IS NULL OR churn_date > DATE(2024,12,31) THEN user_id END) / COUNT_DISTINCT(user_id)` | `mart_user_retention` |
| Total Active Users | `COUNT_DISTINCT(CASE WHEN is_active THEN user_id END)` | `mart_user_retention` |
| RPM | `SUM(total_revenue) / COUNT_DISTINCT(CASE WHEN is_active THEN user_id END) * 1000` | `mart_user_retention` |
| Monthly Active Users | `COUNT_DISTINCT(user_id)` by `month` | `mart_streaming_flat` |
| Skip Rate % | `AVG(CASE WHEN is_skipped THEN 1 ELSE 0 END)` | `mart_streaming_flat` |
| Gross Margin % | `(SUM(revenue_generated) - SUM(royalty_cost)) / SUM(revenue_generated)` | `mart_streaming_flat` |
| Total Revenue | `SUM(revenue_generated)` | `mart_streaming_flat` |
| Like Rate % | `AVG(CASE WHEN is_liked THEN 1 ELSE 0 END)` | `mart_streaming_flat` |
| Streams per Active User | `COUNT(stream_id) / COUNT_DISTINCT(user_id)`, by `month` | `mart_streaming_flat` |
| Avg Streams per Day | `COUNT(stream_id) / COUNT_DISTINCT(listen_date)`, by `is_weekend` | `mart_streaming_flat` |

## Data-verified

Every figure below was read live off the published report and cross-checked against
the **"Regenerated (authoritative)"** column already committed in
[`docs/dashboard.md`](dashboard.md#data-verified) — same live BigQuery data, two
independent BI tools, exact match:

| Measure | Looker Studio (live) | `docs/dashboard.md` regenerated column |
|---|---|---|
| Total Active Users | 43,304 | 43,304 |
| RPM | 128.14 | $128.14 |
| Retention Rate % (year end) | 82.16% | 82.16% |
| Skip Rate % by device (Mobile iOS / Android / Smart Speaker / Tablet / Desktop) | 33% / 33% / 28% / 28% / 28% | 33.0 / 32.9 / 28.1 / 28.0 / 27.9 |
| Total Revenue | 5,548.84 | $5,549 |
| Gross Margin % | 52.43% | 52.4% |
| Skip Rate % by `stream_source` (Algorithmic / Editorial / Search) | ~42% / ~22% / ~22% | 42.0% / 22.1% / 21.9% (`docs/business_questions.md`) |
| Premium vs Free mix (Total Active Users) | Free 45.1%, Premium Individual 29.7%, Premium Student 15%, Premium Family 10.2% | matches the `subscription_plan` split reported in `docs/business_questions.md` |
| Weekend lift (Avg Streams per Day, weekend vs. weekday) | ~3.9K vs. ~3.1K → **+26%** | **+25%** (`docs/business_questions.md` Q10) |
| Like Rate % (overall, avg across genres) | ~13–15% per genre | 14.9% (`docs/dashboard.md`) |
| Streams per Active User by month | low in Feb, peaks Jun–Aug | matches the documented seasonal shape — summer +16%, Feb −19% (`docs/business_questions.md` Q9) |

## Known limitations vs. the Power BI report

- **No native forecast.** The Financials page shows the historical revenue trend only —
  Looker Studio's free tier has no equivalent of Power BI's built-in forecast trend
  lines, unlike the `.pbix`'s Forecast & Financials page.
- **No Key Influencers / Decomposition Tree.** Replaced on the Key Drivers page with
  the raw skip-rate-by-source data plus a citation of the independent skip-prediction
  model, which confirms the same finding by a different method (permutation importance
  vs. this page's plain rate).
