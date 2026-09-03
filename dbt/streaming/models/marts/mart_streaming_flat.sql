-- Denormalized, stream-grain mart for BI tools that don't model stars well
-- (Looker Studio). One row per listening event, every dimension attribute
-- flattened in — no joins required downstream.
with streams as (
    select * from {{ ref('fct_streams') }}
),
tracks as (
    select track_id, main_genre, energy, valence, danceability from {{ ref('stg_tracks') }}
),
users as (
    select user_id, country, subscription_plan from {{ ref('stg_users') }}
),
platforms as (
    select platform_id, service_name from {{ source('raw', 'dim_platform') }}
),
time_dim as (
    select time_key, year, month, day_of_week, is_weekend from {{ source('raw', 'dim_time') }}
)

select
    s.user_id,
    s.track_id,
    s.platform_id,
    s.listen_date,
    s.listen_hour,
    s.device_type,
    s.connection_type,
    s.stream_source,
    s.is_skipped,
    s.is_liked,
    s.listen_duration_sec,
    s.revenue_generated,
    -- FIX 2026-09-03: royalty_cost veniva perso da fct_streams, quindi dopo
    -- dbt il Gross Margin documentato nella dashboard non era calcolabile.
    s.royalty_cost,
    s.completion_ratio,
    s.is_engaged_stream,
    u.country,
    u.subscription_plan,
    t.main_genre,
    t.energy,
    t.valence,
    t.danceability,
    p.service_name,
    d.year,
    d.month,
    d.day_of_week,
    d.is_weekend
from streams s
left join users u on s.user_id = u.user_id
left join tracks t on s.track_id = t.track_id
left join platforms p on s.platform_id = p.platform_id
left join time_dim d on s.listen_date = d.time_key
