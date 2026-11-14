# Warehouse models for Fernwood Pantry

In 2022, I worked hourly with Fernwood Pantry, an e-commerce brand that needed a more reliable and scalable analytics foundation for orders, subscriptions, and marketing. Their reporting was being limited by scattered source data and a refresh cadence that couldn’t keep up with the pace of the business. My goal was to turn their raw operational data into a cleaner, more structured set of tables that could support faster reporting and easier maintenance.

I built a dbt project in BigQuery, with Fivetran handling ingestion from the source systems. The project was organized into three layers: staging, intermediate, and mart. That structure let me separate source cleanup from business logic and reporting-ready outputs, which made the project easier to test and extend over time.

At the staging layer, I standardized field names, types, and basic transformations. In the intermediate layer, I combined related records and applied reusable logic for orders, subscriptions, and marketing. In the mart layer, I shaped the final tables for reporting use cases, keeping the logic modular so each model stayed focused on a single purpose.

A small example of the approach:

```sql
with source as (
    select *
    from {{ ref('stg_orders') }}
),
final as (
    select
        order_id,
        customer_id,
        order_created_at,
        order_status
    from source
)
select * from final
```

Across the project, I delivered 38 models and added tests across 120 columns to help catch issues early and keep the downstream reporting stable. One of the biggest outcomes was improving the dashboard refresh cycle from daily to hourly, which gave Fernwood Pantry much more current visibility into performance.

What I appreciated about this engagement was the balance between clean architecture and practical reporting needs. The final structure was straightforward to maintain, and it gave Fernwood Pantry a much stronger base for ongoing analysis without adding unnecessary complexity.
