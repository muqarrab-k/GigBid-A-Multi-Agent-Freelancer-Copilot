# Shopify customer segments for Juniper & Ash Home

In early 2023, I worked with **Juniper & Ash Home**, an e-commerce brand, on a fixed project to make their Shopify customer data more useful for email marketing and reporting. They had order exports, but the team needed a clearer way to identify which customers were most valuable, how often they were buying, and which groups should receive more focused messaging.

My role was to turn raw Shopify exports into practical customer segments and a simple reporting flow the team could use without extra manual work. I pulled the order data into Google Sheets, cleaned and organized the fields needed for analysis, and built customer groupings based on how recently people had purchased, how often they ordered, and how much they had spent. Those segments were then prepared for the email tool so the marketing team could act on them directly.

I also set up a Looker Studio view so the team could quickly review segment performance and understand where revenue concentration was coming from. The goal was not just to classify customers, but to create something useful for day-to-day campaign planning and reporting.

A simplified version of the setup looked like this:

```txt
Source: Shopify order exports
Fields used: customer_id, order_date, order_count, total_spend
Step 1: Clean and consolidate data in Google Sheets
Step 2: Score customers by recency, frequency, and spend
Step 3: Assign customer segment labels
Step 4: Export segments to the email tool
Step 5: Review performance in Looker Studio
```

The impact was strong and immediate. The top customer segment represented **9% of customers** but generated **41% of revenue**, which gave the team a clear picture of where their most valuable audience sat. After the segments were used in email marketing, **email revenue increased by 19%**.

For Juniper & Ash Home, the project turned Shopify order history into a reusable customer targeting system. It helped the team focus on the customers who mattered most, improve how campaigns were targeted, and connect reporting directly to revenue outcomes.
