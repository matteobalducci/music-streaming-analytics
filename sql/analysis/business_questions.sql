-- =====================================================================
-- Music Streaming Analytics — Business questions answered in SQL
-- Dialect: BigQuery Standard SQL
-- Grain of fct_streams: one row per listening event
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. DISCOVERY EFFICIENCY
-- Is the recommender serving music users actually want, or padding
-- volume with content they skip? Skip rate broken down by source.
-- Expectation: algorithmic skip rate >> user-driven sources.
-- ---------------------------------------------------------------------
SELECT
  stream_source,
  COUNT(*)                                             AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1)       AS skip_rate_pct,
  ROUND(AVG(CAST(is_liked  AS INT64)) * 100, 2)        AS like_rate_pct
FROM `streaming.fct_streams`
GROUP BY stream_source
ORDER BY skip_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q2. CONTENT QUALITY vs VOLUME
-- Which genres drive engaged listening (low skip, high completion)
-- versus genres that generate streams but get skipped?
-- ---------------------------------------------------------------------
SELECT
  t.main_genre,
  COUNT(*)                                                       AS streams,
  ROUND(AVG(CAST(s.is_skipped AS INT64)) * 100, 1)              AS skip_rate_pct,
  ROUND(AVG(s.listen_duration_sec / t.total_duration_sec)*100,1) AS avg_completion_pct
FROM `streaming.fct_streams` s
JOIN `streaming.dim_track`   t USING (track_id)
GROUP BY t.main_genre
ORDER BY streams DESC;


-- ---------------------------------------------------------------------
-- Q3. FRONTLINE vs CATALOG
-- Is growth driven by new releases (frontline) or the back catalog?
-- Different margin/marketing strategies depend on the answer.
-- ---------------------------------------------------------------------
SELECT
  CASE WHEN t.is_frontline THEN 'Frontline (new)' ELSE 'Catalog' END AS release_type,
  COUNT(*)                                                            AS streams,
  ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 1)                    AS share_pct,
  ROUND(AVG(CAST(s.is_skipped AS INT64)) * 100, 1)                   AS skip_rate_pct
FROM `streaming.fct_streams` s
JOIN `streaming.dim_track`   t USING (track_id)
GROUP BY release_type
ORDER BY streams DESC;


-- ---------------------------------------------------------------------
-- Q4. SEASONALITY
-- Monthly volume with weekend lift — capacity & content planning.
-- ---------------------------------------------------------------------
SELECT
  d.month,
  COUNTIF(NOT d.is_weekend)                            AS weekday_streams,
  COUNTIF(d.is_weekend)                                AS weekend_streams,
  COUNT(*)                                             AS total_streams
FROM `streaming.fct_streams` s
JOIN `streaming.dim_time`    d ON s.listen_date = d.time_key
GROUP BY d.month
ORDER BY d.month;


-- ---------------------------------------------------------------------
-- Q5. VIRAL BREAKOUT DETECTION
-- Flag tracks whose monthly streams spike far above their own baseline.
-- Uses a window function to compare each month to the track's median.
-- ---------------------------------------------------------------------
WITH monthly AS (
  SELECT
    s.track_id,
    d.month,
    COUNT(*) AS streams
  FROM `streaming.fct_streams` s
  JOIN `streaming.dim_time`    d ON s.listen_date = d.time_key
  GROUP BY s.track_id, d.month
),
baseline AS (
  SELECT
    track_id,
    month,
    streams,
    AVG(streams) OVER (PARTITION BY track_id) AS avg_monthly_streams
  FROM monthly
)
SELECT
  b.track_id,
  t.track_title,
  b.month,
  b.streams,
  ROUND(b.streams / b.avg_monthly_streams, 1) AS spike_ratio
FROM baseline b
JOIN `streaming.dim_track` t USING (track_id)
WHERE b.streams / b.avg_monthly_streams >= 3      -- 3x its own baseline = breakout
ORDER BY spike_ratio DESC
LIMIT 20;


-- ---------------------------------------------------------------------
-- Q6. CIRCADIAN LISTENING
-- When do people listen? Peak hours drive push-notification timing
-- and editorial playlist scheduling.
-- ---------------------------------------------------------------------
SELECT
  listen_hour,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY listen_hour
ORDER BY listen_hour;


-- ---------------------------------------------------------------------
-- Q7. SUBSCRIBER vs FREE behaviour
-- Do paying users behave differently? Informs conversion strategy.
-- ---------------------------------------------------------------------
SELECT
  is_subscriber,
  COUNT(DISTINCT user_id)                         AS users,
  COUNT(*)                                        AS streams,
  ROUND(COUNT(*) / COUNT(DISTINCT user_id), 1)    AS streams_per_user,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1)  AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY is_subscriber;
