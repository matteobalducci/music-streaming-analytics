-- Fact table: one row per listening event, enriched with a
-- completion ratio and an engagement flag derived at load time.
with streams as (
    select * from {{ ref('stg_streams') }}
),

tracks as (
    select track_id, total_duration_sec from {{ ref('stg_tracks') }}
)

select
    s.user_id,
    s.track_id,
    s.platform_id,
    s.listen_date,
    s.listen_hour,
    s.stream_source,
    s.listen_duration_sec,
    s.is_skipped,
    s.is_liked,
    s.is_subscriber,
    -- share of the track actually listened to (capped at 1.0)
    least(safe_divide(s.listen_duration_sec, t.total_duration_sec), 1.0) as completion_ratio,
    -- an "engaged" stream = not skipped and >50% completed
    (not s.is_skipped and safe_divide(s.listen_duration_sec, t.total_duration_sec) > 0.5) as is_engaged_stream
from streams s
left join tracks t using (track_id)
