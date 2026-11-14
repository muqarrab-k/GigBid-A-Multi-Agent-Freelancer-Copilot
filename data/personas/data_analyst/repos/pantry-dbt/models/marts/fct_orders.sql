{{ config(materialized='table') }}

with orders as (

    select
        order_id,
        customer_id,
        subscription_id,
        order_status,
        order_created_at,
        order_updated_at,
        order_total_amount,
        order_currency
    from {{ ref('stg_orders') }}

),

refunds as (

    select
        order_id,
        refund_id,
        refund_status,
        refund_created_at,
        refund_amount
    from {{ ref('stg_refunds') }}

),

subscriptions as (

    select
        subscription_id,
        customer_id as subscription_customer_id,
        subscription_status,
        subscription_started_at,
        subscription_ended_at
    from {{ ref('stg_subscriptions') }}

),

final as (

    select
        o.order_id,
        o.customer_id,
        o.subscription_id,
        s.subscription_status,
        o.order_status,
        o.order_created_at,
        o.order_updated_at,
        o.order_total_amount,
        o.order_currency,
        r.refund_id,
        r.refund_status,
        r.refund_created_at,
        r.refund_amount,
        s.subscription_started_at,
        s.subscription_ended_at,
        case
            when r.refund_id is not null then true
            else false
        end as is_refunded
    from orders as o
    left join refunds as r
        on o.order_id = r.order_id
    left join subscriptions as s
        on o.subscription_id = s.subscription_id

)

select * from final
