-- Clean, typed staging layer for the raw listening events.
with source as (
    select * from {{ source('raw', 'F_Streams') }}
)

select
    stream_id,
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
-- A negative listen duration is corrupt data, not an edge case: it's dropped
-- here. So the drop is never silent, `validate_data.py` fails if even one
-- exists upstream — so in a healthy pipeline this clause never removes a
-- row, and if it ever did, the load would already have stopped earlier.
where listen_duration_sec >= 0
