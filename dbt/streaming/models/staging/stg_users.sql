with source as (
    select * from {{ source('raw', 'D_Users') }}
)

select
    user_id,
    country,
    cast(signup_date as date) as signup_date,
    subscription_plan,
    signup_channel,
    cast(churn_date as date)  as churn_date
from source
