# Grocery demand forecasting for Marrow & Pine Grocers

I worked with **Marrow & Pine Grocers** on a retail forecasting problem that was affecting day-to-day planning. The team needed a better way to anticipate demand at the store and SKU level so they could make more reliable ordering decisions and reduce waste. Before the project, the forecasting process was too manual and the outputs were not consistent enough for operational use.

I built an automated forecasting pipeline in **Python** that generated **weekly store-by-SKU forecasts for 420 SKUs across 31 stores**. The solution combined **LightGBM** and **Prophet** so the models could capture different demand patterns, including store-level and item-level variation. I also set up the workflow in **Airflow** so the forecasts would run on schedule without manual intervention, and I wrote the results back to **BigQuery** for the team to use in their existing reporting and planning processes.

A key part of the work was making sure the forecasts rolled up cleanly across products and locations. That let the team compare totals at different levels while still preserving the detail they needed for store operations. I focused on building something that fit into their regular cadence rather than requiring a new process around it.

Example pipeline config:

```python
forecast_job:
  schedule: "weekly"
  source: bigquery
  models:
    - lightgbm
    - prophet
  output:
    table: forecast.store_sku_weekly
  scope:
    stores: 31
    skus: 420
```

The impact was clear. **WAPE improved from 31% to 19%**, and **spoilage write-offs fell by 11% in the pilot stores**. More importantly, Marrow & Pine Grocers now has a repeatable forecasting workflow that their team can run and trust each week. Instead of assembling forecasts by hand, they can use an automated output in BigQuery to support ordering and inventory decisions with less friction.
