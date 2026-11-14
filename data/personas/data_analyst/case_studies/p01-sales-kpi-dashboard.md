# Sales KPI Dashboard for Marlowe Furniture

In early 2021, I worked with Marlowe Furniture, a retail business that was managing sales performance through 14 separate Excel reports. The reporting process was fragmented, slow to maintain, and made it difficult for the team to get a consistent view of the numbers during monthly close. My goal was to consolidate that reporting into a single, reliable dashboard that could support faster decision-making.

I built one Power BI report using SQL Server as the source layer, with DAX measures to support the key sales KPIs the business needed. I also structured the report around a star-schema design so the data could be refreshed and analyzed cleanly across sales dimensions. Excel remained part of the workflow where needed, but the main reporting experience moved into Power BI, giving Marlowe Furniture one place to review performance instead of switching between multiple files.

A simple example of the approach is below:

```DAX
Total Sales =
SUM ( Sales[NetSales] )

Monthly Sales =
CALCULATE (
    [Total Sales],
    DATEADD ( 'Date'[Date], -1, MONTH )
)

Sales Growth % =
DIVIDE (
    [Total Sales] - [Monthly Sales],
    [Monthly Sales]
)
```

The impact was immediate. I reduced 14 reports into 1 dashboard, which made the reporting process much easier to manage and understand. Just as importantly, monthly close reporting went from 3 days to 4 hours. That time savings gave the finance and sales teams faster access to the same trusted numbers, which improved the pace of review and removed a lot of manual effort from the process.

This project was a strong example of how I approach reporting automation: simplify the source structure, centralize the logic, and deliver a dashboard that is practical for day-to-day business use. For Marlowe Furniture, that meant less time compiling reports and more time using the results.
