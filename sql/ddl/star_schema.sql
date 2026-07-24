-- =====================================================================
-- Star-schema DDL — BigQuery
-- Load the CSVs from data/ into these tables (or use `bq load`).
-- Grain of fct_streams: one row per listening event.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS streaming;

-- Fact table -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.fct_streams (
  user_id             INT64   NOT NULL,   -- FK -> dim_user
  track_id            INT64   NOT NULL,   -- FK -> dim_track
  platform_id         INT64   NOT NULL,   -- FK -> dim_platform
  listen_date         DATE    NOT NULL,   -- FK -> dim_time.time_key
  listen_hour         INT64,              -- 0-23, circadian analysis
  device_type         STRING,             -- Mobile iOS | Mobile Android | Tablet | Desktop | Smart Speaker
  connection_type     STRING,             -- Wifi | Cellular | Offline
  stream_source       STRING,             -- Algorithmic | Editorial | Search
  is_skipped          BOOL,
  is_liked            BOOL,
  listen_duration_sec INT64,
  royalty_cost        FLOAT64,
  revenue_generated   FLOAT64
)
PARTITION BY listen_date
CLUSTER BY track_id, stream_source;

-- Dimension: users ----------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_user (
  user_id           INT64  NOT NULL,
  country           STRING,
  signup_date       DATE,
  subscription_plan STRING,              -- Free | Premium Individual | Premium Student | Premium Family
  signup_channel    STRING,
  churn_date        DATE                 -- for retention / churn analysis
);

-- Dimension: catalog --------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_track (
  track_id           INT64  NOT NULL,
  track_title        STRING,
  artist_id          INT64,
  main_genre         STRING,
  release_date       DATE,
  bpm                INT64,
  energy             FLOAT64,             -- audio features
  valence            FLOAT64,
  danceability       FLOAT64,
  total_duration_sec INT64
);

-- Dimension: platform -------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_platform (
  platform_id  INT64  NOT NULL,
  service_name STRING                    -- Spotify | Apple Music | YouTube Music | SoundCloud
);

-- Dimension: calendar -------------------------------------------------
CREATE TABLE IF NOT EXISTS streaming.dim_time (
  time_key    DATE   NOT NULL,
  year        INT64,
  month       INT64,
  day_of_week STRING,
  is_weekend  BOOL
);
