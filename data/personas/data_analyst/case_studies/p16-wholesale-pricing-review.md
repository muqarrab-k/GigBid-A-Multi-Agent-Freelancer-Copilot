# Wholesale pricing review for Coastline Hardware

I worked with **Coastline Hardware** from **2024-07 to 2024-09** on an hourly engagement focused on wholesale pricing. The core challenge was straightforward but high-impact: the business needed a clearer way to compare cost, selling price, and sales volume across a large product set, so pricing decisions could be made with more confidence and less manual review.

I built an analysis workflow in **SQL, Excel, and Python** that brought the data together at SKU level and made the pricing picture easier to evaluate. The starting point was a structured extract of product, cost, price, and volume data for **300 SKUs**. I used SQL to assemble the source tables into a clean working dataset, then used Python to shape the outputs and support repeatable calculations. Excel was used to review the results and compare pricing scenarios efficiently.

A key part of the work was translating raw commercial data into practical pricing bands. I compared the relationship between unit cost, current price, and sales volume, then grouped SKUs into proposed bands that reflected how the products were performing. That made it easier to see where prices were too compressed, where there was room to adjust upward, and where current pricing needed to be preserved because of volume sensitivity.

Example of the workflow structure:

```sql
WITH sku_base AS (
  SELECT
    sku_id,
    unit_cost,
    unit_price,
    volume
  FROM pricing_source
),
sku_review AS (
  SELECT
    sku_id,
    unit_cost,
    unit_price,
    volume,
    unit_price - unit_cost AS unit_diff
  FROM sku_base
)
SELECT *
FROM sku_review;
```

The result was a practical pricing review that Coastline Hardware could use to update its wholesale price structure. In total, **300 SKUs were repriced**, and the revised pricing contributed to a **2.3-point increase in gross margin**.
