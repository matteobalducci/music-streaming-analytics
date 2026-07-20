-- Product-metric mart: discovery efficiency by source.
-- One row per stream_source with the KPIs a product team reviews weekly.
with streams as (
    select * from {{ ref('fct_streams') }}
)

select
    stream_source,
    count(*)                                              as streams,
    round(avg(cast(is_skipped as int64)) * 100, 1)        as skip_rate_pct,
    round(avg(cast(is_engaged_stream as int64)) * 100, 1) as engaged_rate_pct,
    round(avg(completion_ratio) * 100, 1)                 as avg_completion_pct,
    round(avg(cast(is_liked as int64)) * 100, 2)          as like_rate_pct
from streams
group by stream_source
order by skip_rate_pct desc
