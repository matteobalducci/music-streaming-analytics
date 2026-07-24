-- Clean, typed staging layer for the raw listening events.
with source as (
    select * from {{ source('raw', 'F_Streams') }}
)

select
    user_id,
    track_id,
    platform_id,
    cast(listen_date as date)        as listen_date,
    listen_hour,
    device_type,
    connection_type,
    stream_source,
    cast(is_skipped as bool)         as is_skipped,
    cast(is_liked   as bool)         as is_liked,
    listen_duration_sec,
    royalty_cost,
    revenue_generated
from source
where listen_duration_sec >= 0
