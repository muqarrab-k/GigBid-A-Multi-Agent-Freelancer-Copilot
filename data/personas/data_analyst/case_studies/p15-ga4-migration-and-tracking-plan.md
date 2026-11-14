# GA4 Migration and Reporting Continuity for Verdant Skincare

When Verdant Skincare needed to move from Universal Analytics to GA4, the biggest risk was losing continuity in their reporting during a critical transition. As an e-commerce business, they depended on clean, consistent data to understand customer behavior, monitor store activity, and keep performance reporting stable across periods. I was brought in on a fixed engagement in 2023 to make sure the migration happened before the cutoff without breaking the historical view they relied on.

My job was to create a practical tracking plan and implement the tagging structure in Google Tag Manager, with Google Analytics and BigQuery supporting the wider measurement setup. I mapped the actions that mattered most for the store and translated them into a GA4-ready structure so the business could keep comparing performance year over year. In total, I mapped 46 events and aligned the setup to the new analytics model while preserving reporting continuity.

A key part of the work was making the transition feel invisible to the business side. Rather than treating the migration as a technical swap, I focused on making sure the data would still support day-to-day decisions, trend analysis, and month-over-month review after the changeover. That meant checking the structure carefully, keeping the implementation clear, and validating the setup before the old system was retired.

```json
{
  "event": "purchase",
  "parameters": {
    "currency": "USD",
    "value": "{{DLV - transaction_value}}",
    "items": "{{DLV - items}}"
  }
}
```

The result was a smooth migration to GA4 with no gap in year-on-year reporting. For Verdant Skincare, that meant the team could continue tracking business performance without interruption, keep trust in their reports, and move forward with a measurement setup that matched the new platform before the cutoff.
