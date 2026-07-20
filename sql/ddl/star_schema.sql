-- =====================================================================
-- Star-schema DDL — BigQuery
-- Load the CSVs from data/ into these tables (or use `bq load`).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS streaming;

-- Fact table: one row per listening event ------------------------------
CREATE TABLE IF NOT EXISTS streaming.fct_streams (
  user_id             INT64   NOT NULL,
  track_id            INT64   NOT NULL,   -- FK -> dim_track
  platform_id         INT64   NOT NULL,   -- FK -> dim_platform
  listen_date         DATE    NOT NULL,   -- FK -> dim_time.time_key
  listen_hour         INT64,              -- 0-23, circadian analysis
  stream_source       STRING,             -- Algorithmic | Editorial | Radio | Search
  listen_duration_sec INT64,
  is_skipped          BOOL,
  is_liked            BOOL,
  is_subscriber       BOOL
)
PARTITION BY listen_date
CLUSTER BY track_id, stream_source;

-- Dimension: catalog ---------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_track (
  track_id          INT64  NOT NULL,
  track_title       STRING,
  artist_id         INT64,
  main_genre        STRING,
  total_duration_sec INT64,
  is_frontline      BOOL                  -- new release vs back-catalog
);

-- Dimension: calendar --------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_time (
  time_key    DATE   NOT NULL,
  year        INT64,
  month       INT64,
  day_of_week STRING,
  is_weekend  BOOL
);

-- Dimension: platform --------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_platform (
  platform_id  INT64  NOT NULL,
  service_name STRING                     -- Spotify | Apple Music | ...
);
