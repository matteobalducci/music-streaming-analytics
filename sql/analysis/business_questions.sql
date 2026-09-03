-- =====================================================================
-- Music Streaming Analytics — Business questions answered in SQL
-- Dialect: BigQuery Standard SQL
-- Grain of fct_streams: one row per listening event
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. DISCOVERY EFFICIENCY
-- Is the recommender serving music users want, or padding volume with
-- content they skip? Expectation: algorithmic skip rate >> user-driven.
-- ---------------------------------------------------------------------
SELECT
  stream_source,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct,
  ROUND(AVG(CAST(is_liked  AS INT64)) * 100, 2)  AS like_rate_pct
FROM `streaming.fct_streams`
GROUP BY stream_source
ORDER BY skip_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q2. WHERE DO SKIPS HAPPEN — by device
-- Mobile vs desktop/speaker. Informs where to invest in UX / recommender.
-- ---------------------------------------------------------------------
SELECT
  device_type,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY device_type
ORDER BY skip_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q3. MONETIZATION — revenue & RPM by subscription plan
-- Which plans drive revenue, and what is revenue per 1k active users?
-- ---------------------------------------------------------------------
SELECT
  u.subscription_plan,
  COUNT(DISTINCT s.user_id)                                    AS active_users,
  COUNT(*)                                                     AS streams,
  ROUND(SUM(s.revenue_generated), 2)                           AS revenue,
  ROUND(SUM(s.revenue_generated) / COUNT(DISTINCT s.user_id) * 1000, 2) AS rpm
FROM `streaming.fct_streams` AS s
INNER JOIN `streaming.dim_user`    AS u ON s.user_id = u.user_id
GROUP BY u.subscription_plan
ORDER BY revenue DESC;


-- ---------------------------------------------------------------------
-- Q4. RETENTION / CHURN (done right)
-- The dashboard KPI conflates reach with retention. Real retention uses
-- churn_date: share of users still active at year end.
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                                              AS signed_up,
  COUNTIF(churn_date IS NULL OR churn_date > DATE '2024-12-31')         AS retained_year_end,
  ROUND(COUNTIF(churn_date IS NULL OR churn_date > DATE '2024-12-31')
        / COUNT(*) * 100, 1)                                            AS retention_pct,
  ROUND(COUNTIF(churn_date <= DATE '2024-12-31') / COUNT(*) * 100, 1)   AS churn_pct
FROM `streaming.dim_user`;


-- ---------------------------------------------------------------------
-- Q5. SEASONALITY — monthly volume with weekend lift
-- ---------------------------------------------------------------------
SELECT
  d.month,
  COUNTIF(NOT d.is_weekend) AS weekday_streams,
  COUNTIF(d.is_weekend)     AS weekend_streams,
  COUNT(*)                  AS total_streams
FROM `streaming.fct_streams` AS s
INNER JOIN `streaming.dim_time`    AS d ON s.listen_date = d.time_key
GROUP BY d.month
ORDER BY d.month;


-- ---------------------------------------------------------------------
-- Q6. CONTENT QUALITY by genre — completion vs volume
-- ---------------------------------------------------------------------
SELECT
  t.main_genre,
  COUNT(*)                                                        AS streams,
  ROUND(AVG(CAST(s.is_skipped AS INT64)) * 100, 1)               AS skip_rate_pct,
  ROUND(AVG(SAFE_DIVIDE(s.listen_duration_sec, t.total_duration_sec)) * 100, 1) AS avg_completion_pct
FROM `streaming.fct_streams` AS s
INNER JOIN `streaming.dim_track`   AS t ON s.track_id = t.track_id
GROUP BY t.main_genre
ORDER BY streams DESC;


-- ---------------------------------------------------------------------
-- Q7. CIRCADIAN LISTENING — peak hours for push/editorial timing
-- ---------------------------------------------------------------------
SELECT
  listen_hour,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY listen_hour
ORDER BY listen_hour;


-- ---------------------------------------------------------------------
-- Q8. MONTH-OVER-MONTH RETENTION
-- Added 2026-09-03: docs/business_questions.md quoted a month-over-month
-- range and a seasonal dip that NO query actually computed. A documented
-- number with no query behind it is a claim, not a finding.
--
-- WARNING (bug fixed the same day): with an INNER JOIN between the previous
-- month and the current one the result is always 100%, because the join
-- removes from the DENOMINATOR exactly the users who did not come back —
-- i.e. the only thing retention measures. The denominator has to be the
-- previous month in full.
-- ---------------------------------------------------------------------
WITH active_by_month AS (
  SELECT DISTINCT
    DATE_TRUNC(listen_date, MONTH) AS month,
    user_id
  FROM `streaming.fct_streams`
)

SELECT
  DATE_ADD(prev.month, INTERVAL 1 MONTH)                              AS month,
  COUNT(DISTINCT prev.user_id)                                        AS active_prev_month,
  COUNT(DISTINCT cur.user_id)                                         AS returned,
  ROUND(COUNT(DISTINCT cur.user_id)
        / NULLIF(COUNT(DISTINCT prev.user_id), 0) * 100, 1)           AS retention_pct
FROM active_by_month AS prev
LEFT JOIN active_by_month AS cur
  ON prev.user_id = cur.user_id
 AND DATE_ADD(prev.month, INTERVAL 1 MONTH) = cur.month
-- The last month has no following month to compare against: without this
-- filter the query emitted a final row at 0.0% that looked like a retention
-- collapse and was actually just the end of the data.
WHERE prev.month < (SELECT MAX(m.month) FROM active_by_month AS m)
GROUP BY prev.month
ORDER BY month;


-- ---------------------------------------------------------------------
-- Q9. SEASONALITY NORMALISED BY ACTIVE USERS
-- Added 2026-09-03. Raw monthly volume is dominated by user-base GROWTH,
-- not by season: August's streams are triple January's mostly because there
-- are twice as many users. Seasonality only shows up once divided by the
-- users active in that month.
-- ---------------------------------------------------------------------
WITH by_month AS (
  SELECT
    DATE_TRUNC(listen_date, MONTH) AS month,
    COUNT(*)                       AS streams,
    COUNT(DISTINCT user_id)        AS active_users
  FROM `streaming.fct_streams`
  GROUP BY month
)

SELECT
  month,
  streams,
  active_users,
  ROUND(streams / active_users, 2)                                    AS streams_per_user,
  ROUND((streams / active_users)
        / AVG(streams / active_users) OVER () * 100, 0)               AS seasonal_index
FROM by_month
ORDER BY month;


-- ---------------------------------------------------------------------
-- Q10. WEEKEND LIFT, PER DAY
-- Added 2026-09-03: Q5 returned weekend and weekday TOTALS, which aren't
-- comparable — a month has ~22 weekdays and ~9 weekend days. The lift needs
-- the PER-DAY average.
-- ---------------------------------------------------------------------
-- Weekend is read from dim_time, not from EXTRACT(DAYOFWEEK): day numbering
-- differs across engines — 1 is Sunday in BigQuery, Monday elsewhere — so
-- `IN (1, 7)` means different things depending on where it runs. The
-- calendar dimension already has the column, and it's the right place to
-- read it from: that's exactly why it exists.
WITH by_day AS (
  SELECT
    f.listen_date,
    d.is_weekend,
    COUNT(*) AS streams
  FROM `streaming.fct_streams` AS f
  INNER JOIN `streaming.dim_time`    AS d ON f.listen_date = d.time_key
  GROUP BY f.listen_date, d.is_weekend
)

SELECT
  ROUND(AVG(IF(is_weekend, streams, NULL)), 0)                        AS weekend_avg,
  ROUND(AVG(IF(is_weekend, NULL, streams)), 0)                        AS weekday_avg,
  ROUND(AVG(IF(is_weekend, streams, NULL))
        / AVG(IF(is_weekend, NULL, streams)) * 100 - 100, 1)          AS lift_pct
FROM by_day;
