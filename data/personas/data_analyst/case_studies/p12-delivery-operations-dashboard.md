# Delivery operations dashboard for Ferrylane Freight

Ferrylane Freight needed a clearer way to track delivery performance across its logistics operations. The team was working with operational data, but it was difficult to get a daily view that could quickly show where delays were happening and which parts of the network needed attention. My goal was to turn that data into a dashboard the team could rely on every day, without adding extra manual reporting work.

I worked with Ferrylane Freight on an hourly engagement from 2023-08 to 2023-11, using PostgreSQL, SQL, and Power BI. I built a daily on-time delivery dashboard organized by depot, driver, and customer so the team could review performance from the perspectives that mattered most to their operation. The reporting setup was designed to stay current as new delivery data came in, so the team could focus on action instead of waiting for manual updates.

A key part of the work was making sure the dashboard supported regular use by operations staff. I structured the data model and reporting logic so the visualizations stayed responsive while covering day-by-day delivery activity. That meant Ferrylane Freight could use the dashboard as part of its routine review process, rather than treating reporting as a separate task.

Example of the SQL pattern used to prepare the delivery dataset:

```sql
SELECT
  delivery_date,
  depot,
  driver,
  customer,
  CASE
    WHEN actual_delivery_time <= promised_delivery_time THEN 1
    ELSE 0
  END AS on_time_flag
FROM delivery_events
WHERE delivery_date >= CURRENT_DATE - INTERVAL '30 days';
```

The result was a practical dashboard the team could use to spot delays by depot, driver, and customer and discuss them with current information in hand. Over the following quarter, late deliveries were down 9%. Just as importantly, Ferrylane Freight now has a daily reporting view that fits into how the team works: checking performance, identifying issues earlier, and using one shared source of truth for delivery operations.
