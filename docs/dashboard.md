# Power BI dashboard — contents

The report ([`dashboard/Music_Stream_Dashboard.pbix`](../dashboard/Music_Stream_Dashboard.pbix))
is built on a Power BI data model with **5 tables**: `F_Streams` (fact) plus
`D_Users`, `D_Tracks`, `D_Platform`, `D_Time`.

**Which layer the report reads, and why.** It connects to the raw star schema that
`scripts/load_bigquery.py` lands in BigQuery — `F_Streams` and the four dimensions —
not to the dbt marts. Power BI models a star natively and computes its measures in
DAX, so routing it through `mart_streaming_flat` (built for tools that flatten a star
badly, such as Looker Studio) would denormalise data the report is happier modelling
itself. The dbt layer is the tested, typed path used for SQL analysis and for any
downstream tool that needs one wide table; both read the same loaded data. The README's
lineage diagram shows the full pipeline, of which the report uses the left-hand branch. *Auto Date/Time is disabled* in
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

Every KPI was checked against the data loaded in BigQuery, which is the dataset this
`.pbix` was built on: Total Active Users 43,803, Total Streams 1,227,355, Retention Rate
82.28% at year end, skip rate by device 33/33/28/28/28, and the Key Influencers finding
`stream_source is Algorithmic → 1.91x` (cross-validated independently by the
[skip-prediction model](../../streaming-insights-copilot)).

**Those four absolute counts are not reproducible from this repository**, and saying so
is more useful than quietly leaving them. They come from a version of the generator that
no longer exists in the source; `make generate` produces 1,215,000 streams, 44,509 active
users and 82.16% retention. Every *rate* the report is built on — skip by source and
device, retention, the subscription mix, the seasonal shape — reproduces within 0.3pp and
is asserted by `tests/test_headline_metrics.py`. The counts differ by ~1%, the findings
do not.

**Regenerating the data moves these figures slightly.** `make generate` produces 1,215,000
streams and 44,509 active users against the 1,227,355 and 43,803 loaded — a ~1% difference
from an earlier version of the generator that is not recoverable from the current source.
The distributions match within 0.3pp, so every skip rate, retention figure and ranking on
the report is unchanged.

**The revenue measures are the exception, and deliberately so.** `revenue_generated` used
to be drawn from the same uniform distribution for every stream regardless of plan, which
made the report's own conclusion — that Premium drives the paid revenue — unmeasurable in
the data behind it. Revenue per stream is now set by plan (Premium Individual ~0.0079 against
Free ~0.0018) and royalty is charged only on a stream that was actually listened to rather
than skipped. RPM therefore reads **$124.72** on regenerated data against $149.19 in the
`.pbix`, and Gross Margin **52.4%** against the flat 32% implied by a royalty applied to
every row. The new figures are the ones the finding rests on; the `.pbix` will show them
after a refresh against reloaded data.

## Known limitation

Listening hour is close to uniform in this dataset (no circadian dip) — the "Streams by
Hour of Day" chart is correctly close to flat. Real temporal patterns in this data are
seasonality (summer/December lift) and a weekend lift, both visible elsewhere in the report.
