# Support Ticket Analytics for Clipboardly

In early 2025, Clipboardly brought me in on a fixed engagement to help make their support data easier to trust and act on. As a productivity software company, they had a growing volume of Zendesk activity, but the reporting wasn’t giving them a clear picture of where support time was going or which parts of the product were driving repeat work.

My focus was to turn raw ticket data into something the team could actually use in daily operations. I worked in SQL to extract and reshape Zendesk records, then built a Power BI dashboard around support response performance and backlog trends. A key part of the project was cleaning up the tag structure behind the tickets so that product areas were represented consistently instead of being split across many near-duplicate labels.

I started by standardizing support tags in SQL and mapping them into a smaller set of product-area groupings. That made it possible to build reliable views for response times, open backlog, and ticket volume by area. From there, I modeled the data for Power BI so the dashboard could show both high-level support health and more detailed breakdowns without needing manual spreadsheet work.

A simple version of the transformation looked like this:

```sql
SELECT
  ticket_id,
  created_at,
  first_response_at,
  CASE
    WHEN tag IN ('billing', 'invoice') THEN 'Billing'
    WHEN tag IN ('login', 'auth') THEN 'Access'
    ELSE 'Other'
  END AS product_area
FROM zendesk_tickets
WHERE status <> 'deleted';
```

The final dashboard gave Clipboardly a clearer view of response times and backlog by product area, with the cleaned-up label structure making the analysis much more reliable. It also helped the team see the operational impact of staffing changes more quickly. After those changes were made, first response time went down 27% based on what the dashboard was showing.

What I liked about this project was that the value came from a practical data layer, not just the visuals. By tightening the SQL logic and structuring the Power BI model around support operations, I gave Clipboardly a reporting setup they could use to monitor support more confidently and respond faster to workload shifts.
