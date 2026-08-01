-- User-grain mart: one row per user, for retention/active-user/monetization
-- metrics that don't belong at the stream grain. Deliberately separate from
-- mart_streaming_flat — mixing grains in one table invites double-counting.
with users as (
    select * from {{ ref('stg_users') }}
),
user_activity as (
    select
        user_id,
        count(*)                    as total_streams,
        sum(revenue_generated)      as total_revenue,
        min(listen_date)            as first_stream_date,
        max(listen_date)            as last_stream_date
    from {{ ref('fct_streams') }}
    group by user_id
)

select
    u.user_id,
    u.country,
    u.signup_date,
    u.subscription_plan,
    u.signup_channel,
    u.churn_date,
    -- Retention is point-in-time (retained-as-of a chosen date), so it's a
    -- calculated field in the BI tool against churn_date, not baked in here.
    coalesce(a.total_streams, 0)   as total_streams,
    coalesce(a.total_revenue, 0.0) as total_revenue,
    a.first_stream_date,
    a.last_stream_date,
    (a.user_id is not null) as is_active
from users u
left join user_activity a on u.user_id = a.user_id
