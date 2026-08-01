# Power BI dashboard — contents

The report ([`dashboard/Music_Stream_Dashboard.pbix`](../dashboard/Music_Stream_Dashboard.pbix))
is built on a Power BI data model with **5 tables**: `F_Streams` (fact) plus
`D_Users`, `D_Tracks`, `D_Platform`, `D_Time`. *Auto Date/Time is disabled* in
favour of an explicit `D_Time` calendar, so month ordering and time hierarchies
are controlled via Sort-by-Column.

> **Data files:** this repo ships all four dimensions (`D_Users`, `D_Tracks`,
> `D_Platform`, `D_Time`) plus a 100k-row real sample of the fact table. The
> **full fact table** (1.23M rows, 97 MB) is published as a
> [GitHub Release asset](../../releases) rather than committed to git history.

## Pages (4)

| # | Page | Contents |
|---|---|---|
| 1 | **Growth & Monetization** | 3 KPI cards (Total Active Users, RPM, **Retention Rate %**), `Monthly Active Users Growth` (line), `Premium vs Free Mix` (donut), `Retention Rate Trend` (line, churn-based) |
| 2 | **Deep Dive & Engagement** | `Streams by Hour of Day` (area, zero-based axis), `Skip Rate %` by device, `Like Rate %` (scatter), `Main Genre` (treemap), map, Country + Genre slicers |
| 3 | **Forecast & Financials** | 3 KPI cards (Total Revenue, RPM, Gross Margin %), `Total Revenue by Year and Quarter` with native Power BI forecast (short horizon, ~2 quarters ahead — appropriate given only 4 quarters of history), revenue by subscription plan, revenue by country (map) |
| 4 | **Machine Learning Insights** | `Key Influencers` (explains `is_skipped`, includes `stream_source`) and `Decomposition Tree` — Power BI's built-in ML visuals for driver analysis and executive drill-down |

## Key measures (DAX)

| Measure | Definition | Why it matters |
|---|---|---|
| **Total Active Users** | `DISTINCTCOUNT(F_Streams[user_id])` | Counts users who actually streamed, not sign-ups — a stickiness signal |
| **RPM** (revenue per 1k users) | `SUM(revenue_generated) / Total Active Users * 1000` | Monetization efficiency; rising users with flat RPM means low-value acquisition |
| **Retention Rate %** | `Retained Users / DISTINCTCOUNT(D_Users[user_id])`, where retained = `churn_date` blank or after period end | Real, churn-based retention (~82% at year end) — *not* the "% who ever listened" a naïve `active / signed-up` reports |
| **Total Revenue / Gross Margin %** | `SUM(revenue_generated)`, `(Revenue − Royalty Cost) / Revenue` | Financial view backing the Forecast page |

## Data-verified

Every KPI on the dashboard has been checked against the source data and matches exactly:
Total Active Users (43,803 ≈ 44K), Total Streams (1,227,355), RPM ($149.19), Retention Rate
(82.28% at year end, 92.27% in April), skip rate by device (33%/33%/28%/28%/28%), revenue
by subscription plan, and the Key Influencers `stream_source is Algorithmic → 1.91x` finding
(cross-validated independently by the [skip-prediction model](../../streaming-insights-copilot)
in the companion Copilot project, which finds `stream_source` the dominant predictor via
permutation importance).

## Known limitation

Listening hour is close to uniform in this dataset (no circadian dip) — the "Streams by
Hour of Day" chart is correctly close to flat. Real temporal patterns in this data are
seasonality (summer/December lift) and a weekend lift, both visible elsewhere in the report.
