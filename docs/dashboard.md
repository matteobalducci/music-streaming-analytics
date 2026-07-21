# Power BI dashboard — contents

The report ([`dashboard/Music_Stream_Dashboard.pbix`](../dashboard/Music_Stream_Dashboard.pbix))
is built on a Power BI data model with **5 tables**: `F_Streams` (fact) plus
`D_Users`, `D_Tracks`, `D_Platform`, `D_Time`. *Auto Date/Time is disabled* in
favour of an explicit `D_Time` calendar, so month ordering and time hierarchies
are controlled via Sort-by-Column.

> **Note on the data files:** this repo ships `D_Tracks`, `D_Platform`, `D_Time`
> and the fact table. `D_Users` lives inside the `.pbix` model and has no CSV in
> `data/` yet — the user-level pages (active users, revenue, retention) depend on it.

## Pages

| # | Page | Status | Contents |
|---|---|---|---|
| 1 | **Growth & Monetization** | ✅ | 3 KPI cards, `Monthly Active Users Growth` (line), `Premium vs Free Mix` (donut), `Retention Rate Trend` (bar), slicer |
| 2 | **Deep Dive & Engagement** | ✅ | `Skip Rate %` (bar), `Like Rate %` (scatter), `Main Genre` (treemap), `Total Streams` (area), map, Country + Genre slicers |
| 3 | **Machine Learning Insights** | ✅ | `Key Influencers` and `Decomposition Tree` — Power BI's built-in ML visuals for driver analysis and executive drill-down |
| 4 | **Forecast & Financials** | ⬜ **empty** | Planned: revenue forecast and financial KPIs |

Four additional *Appunti* pages hold study notes (star schema rationale, DAX
formulas, interview talking points). They are working notes, not part of the
report — consider hiding them before sharing the dashboard publicly.

## Key measures (DAX)

| Measure | Definition | Why it matters |
|---|---|---|
| **Total Active Users** | `DISTINCTCOUNT(F_Streams[user_id])` | Counts users who actually streamed, not sign-ups — a stickiness signal |
| **RPM** (revenue per 1k users) | `SUM(Revenue) / Total Active Users * 1000` | Monetization efficiency; rising users with flat RPM means low-value acquisition |
| **Avg Retention Rate** | `Active Users / Total Signed-Up Users` | Retention against a simulated ~18% churn |

## To finish

- [ ] Build the **Forecast & Financials** page (revenue forecast + financial KPIs)
- [ ] Add `D_Users.csv` to `data/` so the model is reproducible from this repo
- [ ] Hide or remove the *Appunti* note pages in the published version
- [ ] Publish to Power BI Service / Tableau Public and link the URL here
