with source as (
    select * from {{ source('raw', 'D_Tracks') }}
)

select
    track_id,
    track_title,
    artist_id,
    main_genre,
    total_duration_sec,
    cast(is_frontline as bool) as is_frontline
from source
