# Weekly Executive KPI Pack for Alder Property Group

When I started with Alder Property Group, their weekly executive reporting process was still being assembled by hand every Monday. The team needed a reliable way to review occupancy, arrears, and maintenance performance without spending the first part of the week pulling figures from multiple places and reworking the same pack over and over.

I built a scheduled KPI pack that brought those numbers together into one consistent flow. The work centered on pulling source data into BigQuery, shaping it into a reporting-ready structure, and then surfacing the final views in Looker Studio. Google Sheets still played a role where lightweight input and review were useful, but the main goal was to remove repetitive manual steps and make the pack dependable week after week.

From a technical perspective, the key was standardizing the logic behind the KPIs so each run produced the same definitions and layout. That meant organizing the source tables in BigQuery, creating a stable set of calculated fields, and connecting them to a Looker Studio dashboard that could be refreshed on a schedule. I focused on making the pack easy for executives to scan quickly while keeping the underlying data model clean enough to support ongoing updates.

A small part of the SQL structure looked like this:

```sql
SELECT
  week_start,
  property_group,
  occupancy_rate,
  arrears_balance,
  maintenance_open_count
FROM reporting.kpi_weekly
WHERE week_start >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 WEEK)
ORDER BY week_start DESC;
```

The finished pack covered 22 KPIs across occupancy, arrears, and maintenance. More importantly, it replaced a process that used to take about 5 hours a week. That gave Alder Property Group a more consistent executive view and freed up time that had previously been spent rebuilding the same weekly pack by hand.
