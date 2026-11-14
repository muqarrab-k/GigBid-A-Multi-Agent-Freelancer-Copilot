# Snowflake cost audit

I worked with a client in fintech (name withheld) on a fixed engagement from 2024-01 to 2024-02 to reduce Snowflake spend without disrupting day-to-day analytics work.

The team already depended on Snowflake heavily, but they did not have a clear view of which scheduled workloads were driving the highest monthly usage. They needed a practical way to identify the most expensive queries and warehouses, then adjust them so the platform could keep supporting reporting and analysis at a lower cost. My role was to investigate usage patterns, pinpoint the biggest cost drivers, and make targeted changes that the team could trust.

I started by reviewing Snowflake query activity and warehouse consumption in SQL, focusing on scheduled jobs and recurring workloads. From there, I isolated the queries that were consuming the most credits and compared them with the warehouses they were running on. In the cases where a query was doing more work than necessary, I rewrote it to be leaner. In the cases where the warehouse size was not a good fit, I resized it so the workload matched the resources more closely.

A simple example of the kind of checks I used is below:

```sql
SELECT
  warehouse_name,
  SUM(credits_used) AS total_credits,
  COUNT(*) AS query_count
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD(month, -1, CURRENT_TIMESTAMP())
GROUP BY warehouse_name
ORDER BY total_credits DESC;
```

What changed for the team was not just the cost profile, but the way they could operate going forward. They now have a clearer understanding of which scheduled processes are expensive, which warehouses carry the most load, and where to review changes before costs drift upward again. That makes it easier for them to maintain reporting and analytics with less guesswork and fewer surprise spikes.

By the end of the engagement, the result was measurable: monthly credits were down 34%.
