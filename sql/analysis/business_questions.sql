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
FROM `streaming.fct_streams` s
JOIN `streaming.dim_user`    u USING (user_id)
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
FROM `streaming.fct_streams` s
JOIN `streaming.dim_time`    d ON s.listen_date = d.time_key
GROUP BY d.month
ORDER BY d.month;


-- ---------------------------------------------------------------------
-- Q6. CONTENT QUALITY by genre — completion vs volume
-- ---------------------------------------------------------------------
SELECT
  t.main_genre,
  COUNT(*)                                                        AS streams,
  ROUND(AVG(CAST(s.is_skipped AS INT64)) * 100, 1)               AS skip_rate_pct,
  ROUND(AVG(s.listen_duration_sec / t.total_duration_sec) * 100, 1) AS avg_completion_pct
FROM `streaming.fct_streams` s
JOIN `streaming.dim_track`   t USING (track_id)
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
