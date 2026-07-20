-- Clean, typed staging layer for the raw listening events.
with source as (
    select * from {{ source('raw', 'F_Streams') }}
)

select
    user_id,
    track_id,
    platform_id,
    cast(listen_date as date)               as listen_date,
    listen_hour,
    stream_source,
    listen_duration_sec,
    cast(is_skipped   as bool)              as is_skipped,
    cast(is_liked     as bool)              as is_liked,
    cast(is_subscriber as bool)             as is_subscriber
from source
-- drop events with impossible durations
where listen_duration_sec >= 0
