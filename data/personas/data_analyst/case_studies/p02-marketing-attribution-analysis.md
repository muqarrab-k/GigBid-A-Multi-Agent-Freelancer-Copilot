# Marketing attribution analysis for Verdant Skincare

Verdant Skincare, an e-commerce brand, came to me with a familiar challenge: their marketing spend was spread across several channels, but their reporting didn’t clearly show which campaigns were actually driving customer value. They wanted a cleaner way to compare channel performance and make budget decisions with more confidence.

I worked on this engagement hourly from 2021-05 to 2021-07, using Google Analytics, BigQuery, Looker Studio, and SQL. My focus was to connect ad platform spend data with GA4 session data so the team could see how different touchpoints contributed across the customer journey, rather than relying on a single source of credit.

I built the analysis in BigQuery by joining spend and session-level data, then structured the logic to compare first-click, last-click, and a position-based view of credit. This gave Verdant Skincare a more practical way to assess which channels were introducing new users, which ones were closing conversions, and where the budget was being over-credited or under-credited.

A simplified version of the SQL approach looked like this:

```sql
SELECT
  campaign,
  session_source,
  COUNT(*) AS sessions,
  SUM(spend) AS spend,
  SUM(CASE WHEN credit_model = 'first_click' THEN credit ELSE 0 END) AS first_click_credit,
  SUM(CASE WHEN credit_model = 'last_click' THEN credit ELSE 0 END) AS last_click_credit
FROM attribution_base
GROUP BY campaign, session_source
ORDER BY spend DESC;
```

After validating the logic, I surfaced the findings in Looker Studio so the marketing team could explore performance by campaign and compare credit models side by side. The dashboard was designed to support faster budget reviews and make the tradeoffs between acquisition and conversion clearer.

The impact was tangible. Verdant Skincare reallocated 18% of its ad budget based on the analysis, and customer acquisition cost fell by 12% the next quarter. For me, the most valuable part of the project was turning fragmented marketing data into reporting that directly supported budget strategy and measurable efficiency gains.
