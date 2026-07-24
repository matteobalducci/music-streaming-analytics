with source as (
    select * from {{ source('raw', 'D_Tracks') }}
)

select
    track_id,
    track_title,
    artist_id,
    main_genre,
    cast(release_date as date) as release_date,
    bpm,
    energy,
    valence,
    danceability,
    total_duration_sec
from source
